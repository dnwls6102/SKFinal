from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from langchain_core.documents import Document


SLACK_API_BASE = "https://slack.com/api"
SLACK_OAUTH_BASE = "https://slack.com/oauth/v2"
KST = ZoneInfo("Asia/Seoul")
SESSION_STORE_PATH = Path(".slack_oauth_sessions.json")
FILE_CACHE_PATH = Path(".slack_file_cache.json")


class SlackOAuthError(RuntimeError):
    pass


@dataclass
class SlackWorkspaceSession:
    team_id: str
    team_name: str
    user_id: str
    user_name: str
    access_token: str


@dataclass
class SlackSharedFileInfo:
    team_id: str
    team_name: str
    channel_id: str
    channel_name: str
    file_id: str
    title: str
    filetype: str
    created_at: str
    permalink: str
    message_ts: str
    message_text: str


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SlackOAuthError(f"{name} 환경변수가 필요합니다.")
    return value


def get_slack_oauth_config() -> dict[str, str]:
    return {
        "client_id": _required_env("SLACK_CLIENT_ID"),
        "client_secret": _required_env("SLACK_CLIENT_SECRET"),
        "redirect_uri": _required_env("SLACK_REDIRECT_URI"),
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

    if provider != "slack":
        return False
    now = int(datetime.now(timezone.utc).timestamp())
    return now - issued_at <= max_age_seconds


def build_login_url() -> str:
    config = get_slack_oauth_config()
    state = _sign_state(
        {
            "provider": "slack",
            "nonce": secrets.token_urlsafe(24),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        },
        config["client_secret"],
    )
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "user_scope": ",".join(
            [
                "channels:read",
                "groups:read",
                "channels:history",
                "groups:history",
                "files:read",
            ]
        ),
        "state": f"slack:{state}",
    }
    return requests.Request("GET", f"{SLACK_OAUTH_BASE}/authorize", params=params).prepare().url


def _api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _decode_api_response(response: requests.Response) -> dict[str, object]:
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok", False):
        raise SlackOAuthError(str(payload.get("error", "slack_api_error")))
    return payload


def exchange_code_for_token(code: str, state: str) -> SlackWorkspaceSession:
    config = get_slack_oauth_config()
    signed_state = state.removeprefix("slack:")
    if not _verify_state(signed_state, config["client_secret"]):
        raise SlackOAuthError("Slack OAuth state 검증에 실패했습니다.")

    response = requests.post(
        f"{SLACK_API_BASE}/oauth.v2.access",
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "redirect_uri": config["redirect_uri"],
        },
        timeout=30,
    )
    payload = _decode_api_response(response)

    authed_user = payload.get("authed_user") or {}
    team = payload.get("team") or {}
    access_token = str(authed_user.get("access_token", "")).strip()
    user_id = str(authed_user.get("id", "")).strip()
    team_id = str(team.get("id", "")).strip()
    team_name = str(team.get("name", "")).strip() or team_id
    if not access_token or not user_id or not team_id:
        raise SlackOAuthError("Slack 사용자 토큰을 받지 못했습니다.")

    auth_payload = auth_test(access_token)
    return SlackWorkspaceSession(
        team_id=team_id,
        team_name=team_name,
        user_id=user_id,
        user_name=str(auth_payload.get("user", "")).strip() or user_id,
        access_token=access_token,
    )


def auth_test(token: str) -> dict[str, object]:
    response = requests.post(
        f"{SLACK_API_BASE}/auth.test",
        headers=_api_headers(token),
        timeout=30,
    )
    return _decode_api_response(response)


def load_saved_sessions() -> dict[str, SlackWorkspaceSession]:
    if not SESSION_STORE_PATH.exists():
        return {}
    try:
        payload = json.loads(SESSION_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        clear_saved_sessions()
        return {}

    sessions: dict[str, SlackWorkspaceSession] = {}
    try:
        for team_id, item in payload.items():
            sessions[team_id] = SlackWorkspaceSession(**item)
    except Exception:
        clear_saved_sessions()
        return {}
    return sessions


def save_session(session: SlackWorkspaceSession) -> None:
    sessions = load_saved_sessions()
    sessions[session.team_id] = session
    payload = {
        team_id: {
            "team_id": saved.team_id,
            "team_name": saved.team_name,
            "user_id": saved.user_id,
            "user_name": saved.user_name,
            "access_token": saved.access_token,
        }
        for team_id, saved in sessions.items()
    }
    SESSION_STORE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_saved_sessions(team_id: str | None = None) -> None:
    if team_id is None:
        if SESSION_STORE_PATH.exists():
            SESSION_STORE_PATH.unlink()
        return

    sessions = load_saved_sessions()
    if team_id not in sessions:
        return
    sessions.pop(team_id, None)
    if not sessions:
        clear_saved_sessions()
        return
    payload = {
        saved_team_id: {
            "team_id": saved.team_id,
            "team_name": saved.team_name,
            "user_id": saved.user_id,
            "user_name": saved.user_name,
            "access_token": saved.access_token,
        }
        for saved_team_id, saved in sessions.items()
    }
    SESSION_STORE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_file_cache(team_id: str, week_key: str) -> list[SlackSharedFileInfo] | None:
    if not FILE_CACHE_PATH.exists():
        return None

    try:
        payload = json.loads(FILE_CACHE_PATH.read_text(encoding="utf-8"))
        cached_items = payload.get(team_id, {}).get(week_key)
        if not isinstance(cached_items, list):
            return None
        return [SlackSharedFileInfo(**item) for item in cached_items]
    except Exception:
        clear_file_cache()
        return None


def save_file_cache(team_id: str, week_key: str, items: list[SlackSharedFileInfo]) -> None:
    try:
        payload = json.loads(FILE_CACHE_PATH.read_text(encoding="utf-8")) if FILE_CACHE_PATH.exists() else {}
    except Exception:
        payload = {}

    payload.setdefault(team_id, {})
    payload[team_id][week_key] = [
        {
            "team_id": item.team_id,
            "team_name": item.team_name,
            "channel_id": item.channel_id,
            "channel_name": item.channel_name,
            "file_id": item.file_id,
            "title": item.title,
            "filetype": item.filetype,
            "created_at": item.created_at,
            "permalink": item.permalink,
            "message_ts": item.message_ts,
            "message_text": item.message_text,
        }
        for item in items
    ]
    FILE_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_file_cache(team_id: str | None = None) -> None:
    if team_id is None:
        if FILE_CACHE_PATH.exists():
            FILE_CACHE_PATH.unlink()
        return

    if not FILE_CACHE_PATH.exists():
        return
    try:
        payload = json.loads(FILE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        clear_file_cache()
        return

    payload.pop(team_id, None)
    if not payload:
        clear_file_cache()
        return
    FILE_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_current_week_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now.astimezone(KST) if now else datetime.now(KST)
    start_of_this_week = datetime.combine(
        (current - timedelta(days=current.weekday())).date(),
        time.min,
        tzinfo=KST,
    )
    start_of_previous_week = start_of_this_week - timedelta(days=7)
    end_of_previous_week = start_of_this_week - timedelta(seconds=1)
    return start_of_previous_week, end_of_previous_week


def _to_slack_timestamp(value: datetime) -> str:
    return str(int(value.timestamp()))


def fetch_channels(token: str) -> list[dict[str, object]]:
    channels: list[dict[str, object]] = []
    cursor = ""
    while True:
        response = requests.get(
            f"{SLACK_API_BASE}/users.conversations",
            headers=_api_headers(token),
            params={
                "types": "public_channel,private_channel",
                "exclude_archived": "true",
                "limit": 200,
                "cursor": cursor,
            },
            timeout=30,
        )
        payload = _decode_api_response(response)
        channels.extend(payload.get("channels", []))
        cursor = str((payload.get("response_metadata") or {}).get("next_cursor", "")).strip()
        if not cursor:
            break

    channels.sort(key=lambda channel: str(channel.get("name", "")).lower())
    return channels


def _fetch_message_text(token: str, channel_id: str, ts: str) -> str:
    response = requests.get(
        f"{SLACK_API_BASE}/conversations.history",
        headers=_api_headers(token),
        params={
            "channel": channel_id,
            "oldest": ts,
            "latest": ts,
            "inclusive": "true",
            "limit": 1,
        },
        timeout=30,
    )
    payload = _decode_api_response(response)
    messages = payload.get("messages", [])
    if not messages:
        return ""
    return str(messages[0].get("text", "")).strip()


def _fetch_file_detail(token: str, file_id: str) -> dict[str, object]:
    response = requests.get(
        f"{SLACK_API_BASE}/files.info",
        headers=_api_headers(token),
        params={"file": file_id},
        timeout=30,
    )
    payload = _decode_api_response(response)
    return dict(payload.get("file", {}))


def _iter_files(token: str, user_id: str, week_start: datetime, week_end: datetime) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    page = 1
    while True:
        response = requests.get(
            f"{SLACK_API_BASE}/files.list",
            headers=_api_headers(token),
            params={
                "user": user_id,
                "ts_from": _to_slack_timestamp(week_start),
                "ts_to": _to_slack_timestamp(week_end),
                "count": 100,
                "page": page,
            },
            timeout=30,
        )
        payload = _decode_api_response(response)
        page_files = payload.get("files", [])
        if not page_files:
            break
        files.extend(page_files)
        paging = payload.get("paging") or {}
        if int(paging.get("pages", page)) <= page:
            break
        page += 1
    return files


def _extract_share_refs(file_info: dict[str, object], selected_channel_ids: set[str] | None) -> list[tuple[str, str]]:
    shares = file_info.get("shares") or {}
    refs: list[tuple[str, str]] = []
    for visibility in ("public", "private"):
        visibility_shares = shares.get(visibility) or {}
        for channel_id, items in visibility_shares.items():
            if selected_channel_ids is not None and channel_id not in selected_channel_ids:
                continue
            for item in items or []:
                ts = str(item.get("ts", "")).strip()
                if ts:
                    refs.append((channel_id, ts))
    return refs


def fetch_weekly_shared_files(
    session: SlackWorkspaceSession,
    channel_lookup: dict[str, str],
    selected_channel_ids: set[str] | None = None,
) -> list[SlackSharedFileInfo]:
    week_start, week_end = get_current_week_range()
    files = _iter_files(session.access_token, session.user_id, week_start, week_end)

    collected: list[SlackSharedFileInfo] = []
    seen: set[tuple[str, str, str]] = set()
    for file_item in files:
        file_id = str(file_item.get("id", "")).strip()
        if not file_id:
            continue

        file_info = _fetch_file_detail(session.access_token, file_id)
        for channel_id, message_ts in _extract_share_refs(file_info, selected_channel_ids):
            dedupe_key = (file_id, channel_id, message_ts)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            message_text = _fetch_message_text(session.access_token, channel_id, message_ts)
            if not message_text:
                continue

            created = datetime.fromtimestamp(int(file_info.get("created", 0)), tz=timezone.utc).astimezone(KST)
            collected.append(
                SlackSharedFileInfo(
                    team_id=session.team_id,
                    team_name=session.team_name,
                    channel_id=channel_id,
                    channel_name=channel_lookup.get(channel_id, channel_id),
                    file_id=file_id,
                    title=str(file_info.get("title") or file_info.get("name") or file_id),
                    filetype=str(file_info.get("filetype", "")),
                    created_at=created.isoformat(),
                    permalink=str(file_info.get("permalink", "")),
                    message_ts=message_ts,
                    message_text=message_text,
                )
            )

    collected.sort(key=lambda item: item.created_at, reverse=True)
    return collected


def slack_documents(items: list[SlackSharedFileInfo]) -> list[Document]:
    documents: list[Document] = []
    for item in items:
        content = (
            f"Workspace: {item.team_name}\n"
            f"Channel: {item.channel_name}\n"
            f"File: {item.title}\n"
            f"File type: {item.filetype}\n"
            f"Created at: {item.created_at}\n"
            f"Message sent with file:\n{item.message_text}"
        )
        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source": f"slack:{item.team_name}/{item.channel_name}",
                    "type": "slack_file_message",
                    "workspace": item.team_name,
                    "channel": item.channel_name,
                    "file_id": item.file_id,
                    "permalink": item.permalink,
                    "message_ts": item.message_ts,
                },
            )
        )
    return documents
