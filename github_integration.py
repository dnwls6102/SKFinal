from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from langchain_core.documents import Document

import cookie_store
from config import get_secret


GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_BASE = "https://github.com/login/oauth"
KST = ZoneInfo("Asia/Seoul")
SESSION_COOKIE_KEY = "github_session"


class GitHubOAuthError(RuntimeError):
    pass


@dataclass
class CommitInfo:
    repo_full_name: str
    sha: str
    message: str
    author_date: str
    url: str


def _required_env(name: str) -> str:
    value = get_secret(name)
    if not value:
        raise GitHubOAuthError(f"{name} 환경변수가 필요합니다.")
    return value


def get_github_oauth_config() -> dict[str, str]:
    return {
        "client_id": _required_env("GITHUB_CLIENT_ID"),
        "client_secret": _required_env("GITHUB_CLIENT_SECRET"),
        "redirect_uri": _required_env("GITHUB_REDIRECT_URI"),
    }


def _sign_state(payload: dict[str, object], secret: str) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    return f"{token}.{signature}"


def _verify_state(state: str, secret: str, max_age_seconds: int = 600) -> bool:
    try:
        token, signature = state.split(".", 1)
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(raw.decode("utf-8"))
        issued_at = int(payload["iat"])
        provider = str(payload["provider"])
    except Exception:
        return False

    if provider != "github":
        return False
    now = int(datetime.now(timezone.utc).timestamp())
    return now - issued_at <= max_age_seconds


def build_login_url() -> str:
    config = get_github_oauth_config()
    state = _sign_state(
        {
            "provider": "github",
            "nonce": secrets.token_urlsafe(24),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        },
        config["client_secret"],
    )
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": "read:user read:org repo",
        "state": f"github:{state}",
        "allow_signup": "true",
    }
    return requests.Request("GET", f"{GITHUB_OAUTH_BASE}/authorize", params=params).prepare().url


def _api_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def exchange_code_for_token(code: str, state: str) -> str:
    config = get_github_oauth_config()
    signed_state = state.removeprefix("github:")
    if not _verify_state(signed_state, config["client_secret"]):
        raise GitHubOAuthError("GitHub OAuth state 검증에 실패했습니다.")

    response = requests.post(
        f"{GITHUB_OAUTH_BASE}/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "redirect_uri": config["redirect_uri"],
            "state": signed_state,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise GitHubOAuthError(payload.get("error_description", payload["error"]))
    token = payload.get("access_token")
    if not token:
        raise GitHubOAuthError("GitHub access token을 받지 못했습니다.")
    return token


def fetch_authenticated_user(token: str) -> dict[str, object]:
    response = requests.get(
        f"{GITHUB_API_BASE}/user",
        headers=_api_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def load_saved_session() -> tuple[str, dict[str, object]] | None:
    payload = cookie_store.load_json(SESSION_COOKIE_KEY)
    if not isinstance(payload, dict):
        return None
    try:
        token = str(payload["token"])
        user = dict(payload["user"])
    except (KeyError, TypeError, ValueError):
        clear_saved_session()
        return None
    return token, user


def save_session(token: str, user: dict[str, object]) -> None:
    cookie_store.save_json(SESSION_COOKIE_KEY, {"token": token, "user": user})


def clear_saved_session() -> None:
    cookie_store.save_json(SESSION_COOKIE_KEY, None)



def _paginate(url: str, token: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    page = 1
    while True:
        merged = {"per_page": 100, "page": page}
        if params:
            merged.update(params)
        response = requests.get(url, headers=_api_headers(token), params=merged, timeout=30)
        if response.status_code == 409:
            return []
        response.raise_for_status()
        page_items = response.json()
        if not isinstance(page_items, list) or not page_items:
            break
        results.extend(page_items)
        if len(page_items) < 100:
            break
        page += 1
    return results


def fetch_user_repositories(token: str) -> list[dict[str, object]]:
    repos = _paginate(
        f"{GITHUB_API_BASE}/user/repos",
        token,
        params={
            "visibility": "all",
            "affiliation": "owner,collaborator,organization_member",
            "sort": "pushed",
            "direction": "desc",
        },
    )
    repos.sort(key=lambda repo: str(repo["full_name"]).lower())
    return repos


def fetch_user_orgs(token: str) -> list[dict[str, object]]:
    orgs = _paginate(f"{GITHUB_API_BASE}/user/orgs", token)
    orgs.sort(key=lambda org: str(org["login"]).lower())
    return orgs


def get_current_week_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now.astimezone(KST) if now else datetime.now(KST)
    start_of_this_week = datetime.combine(
        (current - timedelta(days=current.weekday())).date(),
        time.min,
        tzinfo=KST,
    )
    return start_of_this_week, current


def _to_github_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_weekly_commits(token: str, username: str, selected_repo_full_names: set[str] | None = None) -> list[CommitInfo]:
    week_start, week_end = get_current_week_range()
    repos = fetch_user_repositories(token)

    commits: list[CommitInfo] = []
    seen: set[str] = set()
    for repo in repos:
        repo_full_name = str(repo["full_name"])
        if selected_repo_full_names is not None and repo_full_name not in selected_repo_full_names:
            continue
        owner = repo["owner"]["login"]
        name = repo["name"]
        commit_items = _paginate(
            f"{GITHUB_API_BASE}/repos/{owner}/{name}/commits",
            token,
            params={
                "author": username,
                "since": _to_github_timestamp(week_start),
                "until": _to_github_timestamp(week_end),
            },
        )
        for item in commit_items:
            sha = item["sha"]
            if sha in seen:
                continue
            seen.add(sha)
            commits.append(
                CommitInfo(
                    repo_full_name=repo_full_name,
                    sha=sha,
                    message=item["commit"]["message"],
                    author_date=item["commit"]["author"]["date"],
                    url=item["html_url"],
                )
            )

    commits.sort(key=lambda commit: commit.author_date, reverse=True)
    return commits


def commit_documents(commits: list[CommitInfo]) -> list[Document]:
    docs: list[Document] = []
    for commit in commits:
        content = (
            f"Repository: {commit.repo_full_name}\n"
            f"Date: {commit.author_date}\n"
            f"Commit SHA: {commit.sha}\n"
            f"Commit message:\n{commit.message}"
        )
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "source": f"github:{commit.repo_full_name}",
                    "type": "github_commit",
                    "sha": commit.sha,
                    "url": commit.url,
                    "author_date": commit.author_date,
                },
            )
        )
    return docs
