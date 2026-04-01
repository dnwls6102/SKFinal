from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from github_integration import (
    GitHubOAuthError,
    build_login_url as build_github_login_url,
    clear_commit_cache,
    clear_saved_session as clear_github_saved_session,
    commit_documents,
    exchange_code_for_token as exchange_github_code_for_token,
    fetch_authenticated_user,
    fetch_user_orgs,
    fetch_user_repositories,
    fetch_weekly_commits,
    get_current_week_range as get_github_week_range,
    load_commit_cache,
    load_saved_session as load_github_saved_session,
    save_commit_cache,
    save_session as save_github_session,
)
from loaders import load_documents
from rag_pipeline import generate_weekly_report
from slack_integration import (
    SlackOAuthError,
    SlackWorkspaceSession,
    auth_test as slack_auth_test,
    build_login_url as build_slack_login_url,
    clear_file_cache as clear_slack_file_cache,
    clear_saved_sessions as clear_slack_saved_sessions,
    exchange_code_for_token as exchange_slack_code_for_token,
    fetch_channels,
    fetch_weekly_shared_files,
    get_current_week_range as get_slack_week_range,
    load_file_cache as load_slack_file_cache,
    load_saved_sessions as load_slack_saved_sessions,
    save_file_cache as save_slack_file_cache,
    save_session as save_slack_session,
    slack_documents,
)


load_dotenv()


def _origin_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


allowed_origins = {
    "http://127.0.0.1:8501",
    "http://localhost:8501",
}
for env_name in ("GITHUB_REDIRECT_URI", "SLACK_REDIRECT_URI"):
    origin = _origin_from_url(os.getenv(env_name, "").strip())
    if origin:
        allowed_origins.add(origin)


app = FastAPI(title="Weekly Report API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OAuthExchangeRequest(BaseModel):
    code: str
    state: str


class GitHubCommitRequest(BaseModel):
    selected_repo_full_names: list[str] = Field(default_factory=list)
    refresh: bool = False


class SlackItemRequest(BaseModel):
    selected_channel_ids: list[str] = Field(default_factory=list)
    refresh: bool = False


def _raise_http_error(status_code: int, detail: str) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def _handle_requests_error(provider: str, exc: requests.RequestException) -> None:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status_code = exc.response.status_code
        detail = f"{provider} API request failed with status {status_code}"
        try:
            payload = exc.response.json()
            if isinstance(payload, dict):
                detail = str(
                    payload.get("message")
                    or payload.get("error")
                    or payload.get("detail")
                    or detail
                )
        except Exception:
            response_text = exc.response.text.strip()
            if response_text:
                detail = response_text[:300]
        _raise_http_error(status_code, detail)

    _raise_http_error(502, f"{provider} API connection failed: {exc}")


def _github_session() -> tuple[str, dict[str, object]] | None:
    saved = load_github_saved_session()
    if not saved:
        return None

    token, user = saved
    try:
        verified_user = fetch_authenticated_user(token)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in {401, 403}:
            clear_github_saved_session()
            clear_commit_cache()
            return None
        raise
    except requests.RequestException:
        verified_user = user

    if verified_user != user:
        save_github_session(token, verified_user)
    return token, verified_user


def _get_github_session_or_401() -> tuple[str, dict[str, object]]:
    session = _github_session()
    if not session:
        _raise_http_error(401, "GitHub session not found")
    return session


def _build_repo_groups(repos: list[dict[str, object]], orgs: list[dict[str, object]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {"개인": []}
    for org in orgs:
        login = str(org.get("login", "")).strip()
        if login:
            groups[login] = []

    for repo in repos:
        repo_name = str(repo["full_name"])
        owner = repo.get("owner", {})
        owner_login = str(owner.get("login", "")).strip()
        owner_type = str(owner.get("type", ""))
        group_name = owner_login if owner_type == "Organization" and owner_login in groups else "개인"
        groups.setdefault(group_name, []).append(repo_name)

    ordered = {"개인": sorted(groups.get("개인", []), key=str.lower)}
    for name in sorted((item for item in groups.keys() if item != "개인"), key=str.lower):
        ordered[name] = sorted(groups[name], key=str.lower)
    return ordered


def _get_github_commits(selected_repo_full_names: list[str], refresh: bool) -> dict[str, Any]:
    token, user = _get_github_session_or_401()
    week_start, week_end = get_github_week_range()
    week_key = week_start.strftime("%Y-%m-%d")
    username = str(user["login"])

    all_commits = None if refresh else load_commit_cache(username, week_key)
    if all_commits is None:
        try:
            all_commits = fetch_weekly_commits(token, username)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {401, 403}:
                clear_github_saved_session()
                clear_commit_cache()
                _raise_http_error(401, "GitHub session expired")
            raise
        save_commit_cache(username, week_key, all_commits)

    selected = set(selected_repo_full_names)
    commits = all_commits if selected_repo_full_names is None else [
        commit for commit in all_commits if commit.repo_full_name in selected
    ]
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_count": len(commits),
        "items": [asdict(commit) for commit in commits],
        "documents": commit_documents(commits),
    }


def _get_slack_session(team_id: str) -> SlackWorkspaceSession:
    sessions = load_slack_saved_sessions()
    session = sessions.get(team_id)
    if not session:
        _raise_http_error(404, "Slack workspace not found")

    try:
        slack_auth_test(session.access_token)
    except SlackOAuthError:
        clear_slack_saved_sessions(team_id)
        clear_slack_file_cache(team_id)
        _raise_http_error(401, "Slack session expired")
    return session


def _get_slack_items(team_id: str, selected_channel_ids: list[str], refresh: bool) -> dict[str, Any]:
    session = _get_slack_session(team_id)
    channels = fetch_channels(session.access_token)
    channel_lookup = {str(channel["id"]): str(channel.get("name", channel["id"])) for channel in channels}
    selected_ids = set(selected_channel_ids)
    week_start, week_end = get_slack_week_range()
    week_key = week_start.strftime("%Y-%m-%d")
    cache_key = f"{week_key}|{','.join(sorted(selected_ids))}"

    all_items = None if refresh else load_slack_file_cache(team_id, cache_key)
    if all_items is None:
        all_items = fetch_weekly_shared_files(session, channel_lookup, selected_ids or None)
        save_slack_file_cache(team_id, cache_key, all_items)

    filtered_items = [item for item in all_items if not selected_ids or item.channel_id in selected_ids]
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_count": len(filtered_items),
        "channels": channels,
        "items": [asdict(item) for item in filtered_items],
        "documents": slack_documents(filtered_items),
    }


def _parse_json_field(raw_value: str, default: Any) -> Any:
    if not raw_value:
        return default
    return json.loads(raw_value)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/github/login-url")
def github_login_url() -> dict[str, str]:
    try:
        return {"url": build_github_login_url()}
    except GitHubOAuthError as exc:
        _raise_http_error(400, str(exc))


@app.post("/github/exchange")
def github_exchange(payload: OAuthExchangeRequest) -> dict[str, object]:
    try:
        token = exchange_github_code_for_token(payload.code, payload.state)
        user = fetch_authenticated_user(token)
    except GitHubOAuthError as exc:
        _raise_http_error(400, str(exc))
    except requests.HTTPError as exc:
        _raise_http_error(exc.response.status_code if exc.response else 500, str(exc))

    save_github_session(token, user)
    return {"connected": True, "user": user}


@app.get("/github/session")
def github_session() -> dict[str, object]:
    session = _github_session()
    if not session:
        return {"connected": False, "user": None}
    _, user = session
    return {"connected": True, "user": user}


@app.delete("/github/session")
def github_disconnect() -> dict[str, bool]:
    clear_github_saved_session()
    clear_commit_cache()
    return {"ok": True}


@app.get("/github/repositories")
def github_repositories() -> dict[str, object]:
    token, _ = _get_github_session_or_401()
    try:
        repos = fetch_user_repositories(token)
        orgs = fetch_user_orgs(token)
    except requests.RequestException as exc:
        _handle_requests_error("GitHub", exc)
    return {
        "repos": repos,
        "orgs": orgs,
        "repo_groups": _build_repo_groups(repos, orgs),
    }


@app.post("/github/commits")
def github_commits(payload: GitHubCommitRequest) -> dict[str, object]:
    try:
        data = _get_github_commits(payload.selected_repo_full_names, payload.refresh)
    except requests.RequestException as exc:
        _handle_requests_error("GitHub", exc)
    return {key: value for key, value in data.items() if key != "documents"}


@app.get("/slack/login-url")
def slack_login_url() -> dict[str, str]:
    try:
        return {"url": build_slack_login_url()}
    except SlackOAuthError as exc:
        _raise_http_error(400, str(exc))


@app.post("/slack/exchange")
def slack_exchange(payload: OAuthExchangeRequest) -> dict[str, object]:
    try:
        session = exchange_slack_code_for_token(payload.code, payload.state)
    except SlackOAuthError as exc:
        _raise_http_error(400, str(exc))

    save_slack_session(session)
    return {"connected": True, "workspace": asdict(session)}


@app.get("/slack/workspaces")
def slack_workspaces() -> dict[str, object]:
    sessions = load_slack_saved_sessions()
    workspaces = [asdict(session) for session in sorted(sessions.values(), key=lambda item: item.team_name.lower())]
    return {"workspaces": workspaces}


@app.delete("/slack/workspaces/{team_id}")
def slack_disconnect(team_id: str) -> dict[str, bool]:
    clear_slack_saved_sessions(team_id)
    clear_slack_file_cache(team_id)
    return {"ok": True}


@app.get("/slack/workspaces/{team_id}/channels")
def slack_channels(team_id: str) -> dict[str, object]:
    session = _get_slack_session(team_id)
    try:
        channels = fetch_channels(session.access_token)
    except requests.RequestException as exc:
        _handle_requests_error("Slack", exc)
    return {"channels": channels}


@app.post("/slack/workspaces/{team_id}/items")
def slack_items(team_id: str, payload: SlackItemRequest) -> dict[str, object]:
    try:
        data = _get_slack_items(team_id, payload.selected_channel_ids, payload.refresh)
    except requests.RequestException as exc:
        _handle_requests_error("Slack", exc)
    return {key: value for key, value in data.items() if key != "documents"}


@app.post("/report/generate")
async def report_generate(
    template_fields: str = Form(...),
    report_style: str = Form("match"),
    selected_repo_full_names: str = Form("[]"),
    selected_team_id: str = Form(""),
    selected_channel_ids: str = Form("[]"),
    example_files: list[UploadFile] | None = File(None),
) -> dict[str, object]:
    parsed_fields = [field.strip() for field in _parse_json_field(template_fields, []) if str(field).strip()]
    if not parsed_fields:
        _raise_http_error(400, "At least one template field is required")

    documents = []
    selected_repos = _parse_json_field(selected_repo_full_names, [])
    selected_channels = _parse_json_field(selected_channel_ids, [])

    github_count = 0
    try:
        github_payload = _get_github_commits(selected_repos, refresh=False) if _github_session() else None
    except requests.RequestException as exc:
        _handle_requests_error("GitHub", exc)
    if github_payload:
        documents.extend(github_payload["documents"])
        github_count = github_payload["total_count"]

    slack_count = 0
    if selected_team_id:
        try:
            slack_payload = _get_slack_items(selected_team_id, selected_channels, refresh=False)
        except requests.RequestException as exc:
            _handle_requests_error("Slack", exc)
        documents.extend(slack_payload["documents"])
        slack_count = slack_payload["total_count"]

    if not documents:
        _raise_http_error(400, "No GitHub or Slack data available for report generation")

    template = "\n\n".join(f"{index + 1}. {field}\n- " for index, field in enumerate(parsed_fields))

    with tempfile.TemporaryDirectory() as tmp_dir:
        saved_paths: list[Path] = []
        for upload in example_files or []:
            if not upload.filename:
                continue
            path = Path(tmp_dir) / upload.filename
            path.write_bytes(await upload.read())
            saved_paths.append(path)

        example_documents = load_documents(saved_paths)

    result = generate_weekly_report(
        documents=documents,
        template=template,
        template_fields=parsed_fields,
        report_style=report_style,
        example_documents=example_documents,
    )

    return {
        "report": result["report"],
        "structured_report": result["structured_report"],
        "queries": result["queries"],
        "metrics": {
            "document_count": len(documents),
            "github_item_count": github_count,
            "slack_item_count": slack_count,
        },
    }
