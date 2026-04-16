from __future__ import annotations

import html
import tempfile
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
from langchain_core.documents import Document

from cookie_store import get_cookies
from example_documents import EXAMPLE_UPLOAD_TYPES, load_example_documents
from github_integration import (
    GitHubOAuthError,
    build_login_url as build_github_login_url,
    clear_saved_session as clear_github_saved_session,
    commit_documents,
    exchange_code_for_token as exchange_github_code_for_token,
    fetch_authenticated_user,
    fetch_user_orgs,
    fetch_user_repositories,
    fetch_weekly_commits,
    get_current_week_range as get_github_week_range,
    load_saved_session as load_github_saved_session,
    save_session as save_github_session,
)
from loaders import load_documents
from rag_pipeline import generate_weekly_report
from slack_integration import (
    SlackOAuthError,
    auth_test as slack_auth_test,
    build_login_url as build_slack_login_url,
    clear_saved_sessions as clear_slack_saved_sessions,
    exchange_code_for_token as exchange_slack_code_for_token,
    fetch_channels,
    fetch_weekly_shared_files,
    get_current_week_range as get_slack_week_range,
    load_saved_sessions as load_slack_saved_sessions,
    save_session as save_slack_session,
    slack_documents,
)


load_dotenv()

st.set_page_config(page_title="Weekly Report RAG", layout="wide")

get_cookies()

DEFAULT_TEMPLATE_FIELDS = [
    "업무 내용 및 활동",
    "성공적으로 잘 수행했다고 생각하는 점",
    "스스로 부족하다고 생각하는 점/보완 계획",
]


def _format_report_generation_error(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "보고서 생성 중 알 수 없는 오류가 발생했습니다."
    return f"보고서 생성 중 오류가 발생했습니다: {message}"


def _clear_github_session_state() -> None:
    for key in (
        "github_token",
        "github_user",
        "github_orgs",
        "github_repos",
        "weekly_commits",
        "all_weekly_commits",
        "selected_repo_groups",
        "weekly_commit_cache_key",
    ):
        st.session_state.pop(key, None)


def _clear_slack_session_state(team_id: str | None = None) -> None:
    if team_id is None:
        st.session_state.pop("slack_selected_team_id", None)

    prefixes = (
        "slack_channels::",
        "slack_selected_channels::",
        "slack_items::",
        "slack_cache_key::",
        "slack_refresh_requested::",
    )
    for key in list(st.session_state.keys()):
        if not any(key.startswith(prefix) for prefix in prefixes):
            continue
        if team_id is None or key.endswith(team_id):
            st.session_state.pop(key, None)


def _bootstrap_github_saved_session() -> None:
    if st.session_state.get("github_token") and st.session_state.get("github_user"):
        return

    saved = load_github_saved_session()
    if not saved:
        return

    token, user = saved
    try:
        verified_user = fetch_authenticated_user(token)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in {401, 403}:
            clear_github_saved_session()
            return
        raise
    except requests.RequestException:
        verified_user = user

    st.session_state["github_token"] = token
    st.session_state["github_user"] = verified_user or user


def _handle_github_oauth_callback() -> None:
    code = st.query_params.get("code")
    state = st.query_params.get("state")
    error = st.query_params.get("error")

    if state and not str(state).startswith("github:"):
        return

    if error:
        st.error(f"GitHub OAuth 오류: {error}")
        st.query_params.clear()
        return

    if not code or not state or st.session_state.get("github_token"):
        return

    try:
        token = exchange_github_code_for_token(code, state)
        user = fetch_authenticated_user(token)
    except GitHubOAuthError as exc:
        st.error(str(exc))
        st.query_params.clear()
        return
    except Exception as exc:
        st.error(f"GitHub 로그인 처리 중 오류가 발생했습니다: {exc}")
        st.query_params.clear()
        return

    st.session_state["github_token"] = token
    st.session_state["github_user"] = user
    st.session_state.pop("github_orgs", None)
    st.session_state.pop("github_repos", None)
    st.session_state.pop("weekly_commits", None)
    st.session_state.pop("all_weekly_commits", None)
    st.session_state.pop("weekly_commit_cache_key", None)
    save_github_session(token, user)
    st.query_params.clear()
    st.rerun()


def _handle_slack_oauth_callback() -> None:
    code = st.query_params.get("code")
    state = st.query_params.get("state")
    error = st.query_params.get("error")

    if state and not str(state).startswith("slack:"):
        return

    if error:
        st.error(f"Slack OAuth 오류: {error}")
        st.query_params.clear()
        return

    if not code or not state:
        return

    try:
        session = exchange_slack_code_for_token(code, state)
    except SlackOAuthError as exc:
        st.error(str(exc))
        st.query_params.clear()
        return
    except Exception as exc:
        st.error(f"Slack 로그인 처리 중 오류가 발생했습니다: {exc}")
        st.query_params.clear()
        return

    save_slack_session(session)
    st.session_state["slack_selected_team_id"] = session.team_id
    _clear_slack_session_state(session.team_id)
    st.query_params.clear()
    st.rerun()


def _load_repositories(token: str) -> list[dict[str, object]]:
    repos = st.session_state.get("github_repos")
    if repos is None:
        repos = fetch_user_repositories(token)
        st.session_state["github_repos"] = repos
    return repos


def _load_orgs(token: str) -> list[dict[str, object]]:
    orgs = st.session_state.get("github_orgs")
    if orgs is None:
        orgs = fetch_user_orgs(token)
        st.session_state["github_orgs"] = orgs
    return orgs


def _load_slack_channels(team_id: str, access_token: str) -> list[dict[str, object]]:
    key = f"slack_channels::{team_id}"
    channels = st.session_state.get(key)
    if channels is None:
        channels = fetch_channels(access_token)
        st.session_state[key] = channels
    return channels


def _build_repo_groups(repos: list[dict[str, object]], orgs: list[dict[str, object]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {"개인": []}
    for org in orgs:
        login = str(org.get("login", "")).strip()
        if login:
            groups[f"조직: {login}"] = []

    for repo in repos:
        repo_name = str(repo["full_name"])
        owner = repo.get("owner", {})
        owner_login = str(owner.get("login", "unknown"))
        owner_type = str(owner.get("type", ""))
        group_name = f"조직: {owner_login}" if owner_type == "Organization" else "개인"
        groups.setdefault(group_name, []).append(repo_name)

    ordered = {"개인": sorted(groups.get("개인", []), key=str.lower)}
    for name in sorted((name for name in groups.keys() if name != "개인"), key=str.lower):
        ordered[name] = sorted(groups[name], key=str.lower)
    return ordered


def _render_repo_group_selection(repos: list[dict[str, object]], orgs: list[dict[str, object]]) -> set[str]:
    grouped_repos = _build_repo_groups(repos, orgs)
    group_names = list(grouped_repos.keys())

    stored_groups = st.session_state.get("selected_repo_groups")
    if not isinstance(stored_groups, set):
        stored_groups = set(group_names)
    else:
        stored_groups = {name for name in stored_groups if name in group_names}
        for name in group_names:
            if name not in stored_groups:
                stored_groups.add(name)
    st.session_state["selected_repo_groups"] = stored_groups

    left, right = st.columns(2)
    with left:
        if st.button("전체 선택", key="github_group_select_all", use_container_width=True):
            st.session_state["selected_repo_groups"] = set(group_names)
    with right:
        if st.button("전체 해제", key="github_group_select_none", use_container_width=True):
            st.session_state["selected_repo_groups"] = set()

    selected_groups = st.session_state["selected_repo_groups"]
    with st.expander("개인/조직 선택", expanded=False):
        for group_name in group_names:
            checked = group_name in selected_groups
            if st.checkbox(group_name, value=checked, key=f"github_group_checkbox::{group_name}"):
                selected_groups.add(group_name)
            else:
                selected_groups.discard(group_name)

    st.session_state["selected_repo_groups"] = selected_groups
    return {
        repo_name
        for group_name in selected_groups
        for repo_name in grouped_repos[group_name]
    }


def _render_slack_channel_selection(team_id: str, channels: list[dict[str, object]]) -> set[str]:
    state_key = f"slack_selected_channels::{team_id}"
    channel_ids = [str(channel["id"]) for channel in channels]
    selected_channels = st.session_state.get(state_key)
    if not isinstance(selected_channels, set):
        selected_channels = set(channel_ids)
    else:
        selected_channels = {channel_id for channel_id in selected_channels if channel_id in channel_ids}
        for channel_id in channel_ids:
            if channel_id not in selected_channels:
                selected_channels.add(channel_id)
    st.session_state[state_key] = selected_channels

    left, right = st.columns(2)
    with left:
        if st.button("전체 선택", key=f"slack_channel_select_all::{team_id}", use_container_width=True):
            st.session_state[state_key] = set(channel_ids)
    with right:
        if st.button("전체 해제", key=f"slack_channel_select_none::{team_id}", use_container_width=True):
            st.session_state[state_key] = set()

    selected_channels = st.session_state[state_key]
    with st.expander("채널 선택", expanded=False):
        for channel in channels:
            channel_id = str(channel["id"])
            channel_name = str(channel.get("name", channel_id))
            checked = channel_id in selected_channels
            if st.checkbox(f"#{channel_name}", value=checked, key=f"slack_channel_checkbox::{team_id}::{channel_id}"):
                selected_channels.add(channel_id)
            else:
                selected_channels.discard(channel_id)

    st.session_state[state_key] = selected_channels
    return selected_channels


def _render_commit_list(commits) -> None:
    items: list[str] = []
    for idx, commit in enumerate(commits, start=1):
        message_html = html.escape(commit.message).replace("\n", "<br>")
        items.append(
            f"""
            <div style="padding:12px 14px;border-bottom:1px solid #e5e7eb;">
              <div style="font-weight:600;margin-bottom:4px;">{idx}. {html.escape(commit.repo_full_name)}</div>
              <div style="font-size:12px;color:#6b7280;margin-bottom:8px;">{html.escape(commit.author_date[:10])}</div>
              <div style="white-space:normal;line-height:1.5;">{message_html}</div>
              <div style="margin-top:8px;font-size:12px;">
                <a href="{html.escape(commit.url)}" target="_blank" style="color:#2563eb;text-decoration:none;">커밋 보기</a>
              </div>
            </div>
            """
        )

    html_block = f"""
    <div style="max-height:420px; overflow-y:auto; border:1px solid #d1d5db; border-radius:10px; background:#ffffff;">
      {''.join(items)}
    </div>
    """
    st.html(html_block)


def _render_slack_item_list(items) -> None:
    blocks: list[str] = []
    for idx, item in enumerate(items, start=1):
        message_html = html.escape(item.message_text).replace("\n", "<br>")
        blocks.append(
            f"""
            <div style="padding:12px 14px;border-bottom:1px solid #e5e7eb;">
              <div style="font-weight:600;margin-bottom:4px;">{idx}. {html.escape(item.channel_name)} / {html.escape(item.title)}</div>
              <div style="font-size:12px;color:#6b7280;margin-bottom:8px;">{html.escape(item.created_at[:10])}</div>
              <div style="white-space:normal;line-height:1.5;margin-bottom:8px;">{message_html}</div>
              <div style="font-size:12px;">
                <a href="{html.escape(item.permalink)}" target="_blank" style="color:#2563eb;text-decoration:none;">Slack 파일 보기</a>
              </div>
            </div>
            """
        )

    html_block = f"""
    <div style="max-height:420px; overflow-y:auto; border:1px solid #d1d5db; border-radius:10px; background:#ffffff;">
      {''.join(blocks)}
    </div>
    """
    st.html(html_block)


def _render_github_section():
    st.subheader("GitHub 연동")
    _bootstrap_github_saved_session()
    _handle_github_oauth_callback()

    token = st.session_state.get("github_token")
    user = st.session_state.get("github_user")

    if not token or not user:
        try:
            login_url = build_github_login_url()
            st.link_button("GitHub 로그인", login_url, use_container_width=True)
            st.caption("한 번 로그인하면 토큰을 로컬 파일에 저장해 다음 실행에서도 로그인 상태를 유지합니다.")
        except GitHubOAuthError as exc:
            st.warning(str(exc))
            st.caption("`.env`에 `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`를 설정해야 합니다.")
        return []

    left, right = st.columns([3, 1])
    with left:
        st.success(f"GitHub 연결됨: {user.get('login')}")
    with right:
        if st.button("연결 해제", key="github_disconnect", use_container_width=True):
            _clear_github_session_state()
            clear_github_saved_session()
            st.query_params.clear()
            st.rerun()

    try:
        orgs = _load_orgs(token)
        repos = _load_repositories(token)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in {401, 403}:
            clear_github_saved_session()
            _clear_github_session_state()
            st.error("저장된 GitHub 로그인 정보가 만료되었습니다. 다시 로그인해야 합니다.")
            return []
        st.error(f"GitHub 데이터 조회 중 오류가 발생했습니다: {exc}")
        return []
    except Exception as exc:
        st.error(f"GitHub 데이터 조회 중 오류가 발생했습니다: {exc}")
        return []

    selected_repos = _render_repo_group_selection(repos, orgs)

    week_start, week_end = get_github_week_range()
    week_key = week_start.strftime("%Y-%m-%d")
    st.caption(f"조회 범위: {week_start:%Y-%m-%d %H:%M} ~ {week_end:%Y-%m-%d %H:%M} (Asia/Seoul 기준)")

    refresh = st.button("이번 주 커밋 새로고침", key="github_refresh", use_container_width=True)
    cache_key_changed = st.session_state.get("weekly_commit_cache_key") != week_key
    if cache_key_changed:
        st.session_state.pop("all_weekly_commits", None)
        st.session_state["weekly_commit_cache_key"] = week_key

    if refresh or "all_weekly_commits" not in st.session_state:
        with st.spinner("GitHub에서 커밋 메시지를 가져오는 중입니다."):
            try:
                all_commits = fetch_weekly_commits(token, str(user["login"]))
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in {401, 403}:
                    clear_github_saved_session()
                    _clear_github_session_state()
                    st.error("저장된 GitHub 로그인 정보가 만료되었습니다. 다시 로그인해야 합니다.")
                    return []
                st.error(f"커밋 조회 중 오류가 발생했습니다: {exc}")
                return []
            except Exception as exc:
                st.error(f"커밋 조회 중 오류가 발생했습니다: {exc}")
                return []

            st.session_state["all_weekly_commits"] = all_commits

    all_commits = st.session_state.get("all_weekly_commits", [])
    commits = [commit for commit in all_commits if commit.repo_full_name in selected_repos]
    st.session_state["weekly_commits"] = commits

    st.write(f"조회된 커밋 수: {len(commits)}")
    if not commits:
        st.info("선택된 그룹 기준 커밋이 없습니다.")
        return []

    _render_commit_list(commits)
    return commit_documents(commits)


def _render_slack_section():
    st.subheader("Slack 연동")
    _handle_slack_oauth_callback()

    sessions = load_slack_saved_sessions()
    workspace_options = sorted(sessions.values(), key=lambda item: item.team_name.lower())

    if not workspace_options:
        try:
            login_url = build_slack_login_url()
            st.link_button("Slack 워크스페이스 연결", login_url, use_container_width=True)
            st.caption("워크스페이스마다 한 번씩 연결해야 합니다. 연결한 워크스페이스는 로컬에 저장됩니다.")
        except SlackOAuthError as exc:
            st.warning(str(exc))
            st.caption("`.env`에 `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI`를 설정해야 합니다.")
        return []

    try:
        add_workspace_url = build_slack_login_url()
    except SlackOAuthError as exc:
        st.warning(str(exc))
        add_workspace_url = None

    if add_workspace_url:
        st.link_button("워크스페이스 추가 연결", add_workspace_url, use_container_width=True)

    team_ids = [session.team_id for session in workspace_options]
    default_team_id = st.session_state.get("slack_selected_team_id", team_ids[0])
    if default_team_id not in team_ids:
        default_team_id = team_ids[0]

    selected_team_id = st.selectbox(
        "워크스페이스",
        options=team_ids,
        index=team_ids.index(default_team_id),
        format_func=lambda team_id: sessions[team_id].team_name,
    )
    st.session_state["slack_selected_team_id"] = selected_team_id
    selected_session = sessions[selected_team_id]

    left, right = st.columns([3, 1])
    with left:
        st.success(f"Slack 연결됨: {selected_session.team_name} / {selected_session.user_name}")
    with right:
        if st.button("연결 해제", key=f"slack_disconnect::{selected_team_id}", use_container_width=True):
            clear_slack_saved_sessions(selected_team_id)
            _clear_slack_session_state(selected_team_id)
            st.rerun()

    refresh = st.button("이번 주 Slack 기록 새로고침", key=f"slack_refresh::{selected_team_id}", use_container_width=True)
    if refresh:
        st.session_state[f"slack_refresh_requested::{selected_team_id}"] = True
        st.session_state.pop(f"slack_channels::{selected_team_id}", None)
        st.session_state.pop(f"slack_selected_channels::{selected_team_id}", None)
        st.rerun()

    try:
        slack_auth_test(selected_session.access_token)
        if st.session_state.get(f"slack_refresh_requested::{selected_team_id}", False):
            st.session_state.pop(f"slack_channels::{selected_team_id}", None)
            st.session_state.pop(f"slack_selected_channels::{selected_team_id}", None)
            st.session_state.pop(f"slack_refresh_requested::{selected_team_id}", None)
        channels = _load_slack_channels(selected_team_id, selected_session.access_token)
    except SlackOAuthError as exc:
        clear_slack_saved_sessions(selected_team_id)
        _clear_slack_session_state(selected_team_id)
        st.error(f"Slack 연결이 만료되었거나 권한이 부족합니다: {exc}")
        return []
    except Exception as exc:
        st.error(f"Slack 채널 조회 중 오류가 발생했습니다: {exc}")
        return []

    if not channels:
        st.info("조회 가능한 채널이 없습니다.")
        return []

    selected_channel_ids = _render_slack_channel_selection(selected_team_id, channels)
    channel_lookup = {str(channel["id"]): str(channel.get("name", channel["id"])) for channel in channels}

    week_start, week_end = get_slack_week_range()
    week_key = week_start.strftime("%Y-%m-%d")
    selected_channels_key = ",".join(sorted(selected_channel_ids))
    effective_cache_key = f"{week_key}|{selected_channels_key}"
    cache_state_key = f"slack_cache_key::{selected_team_id}"
    items_state_key = f"slack_items::{selected_team_id}"
    st.caption(f"조회 범위: {week_start:%Y-%m-%d %H:%M} ~ {week_end:%Y-%m-%d %H:%M} (Asia/Seoul 기준)")

    cache_key_changed = st.session_state.get(cache_state_key) != effective_cache_key
    if cache_key_changed:
        st.session_state.pop(items_state_key, None)
        st.session_state[cache_state_key] = effective_cache_key

    if refresh or items_state_key not in st.session_state:
        with st.spinner("Slack에서 파일과 메시지를 가져오는 중입니다."):
            try:
                all_items = fetch_weekly_shared_files(selected_session, channel_lookup, selected_channel_ids)
            except SlackOAuthError as exc:
                st.error(f"Slack 기록 조회 중 오류가 발생했습니다: {exc}")
                return []
            except Exception as exc:
                st.error(f"Slack 기록 조회 중 오류가 발생했습니다: {exc}")
                return []

            st.session_state[items_state_key] = all_items

    all_items = st.session_state.get(items_state_key, [])
    filtered_items = [item for item in all_items if item.channel_id in selected_channel_ids]

    st.write(f"조회된 Slack 파일/메시지 수: {len(filtered_items)}")
    if not filtered_items:
        st.info("선택된 채널 기준 기록이 없습니다.")
        return []

    _render_slack_item_list(filtered_items)
    return slack_documents(filtered_items)


def _ensure_manual_entries() -> None:
    if "manual_entries" not in st.session_state:
        st.session_state["manual_entries"] = [""]


def _add_manual_entry() -> None:
    st.session_state["manual_entries"] = [*st.session_state["manual_entries"], ""]


def _remove_manual_entry(index: int) -> None:
    entries = list(st.session_state["manual_entries"])
    if len(entries) <= 1:
        st.session_state["manual_entries"] = [""]
    else:
        entries.pop(index)
        st.session_state["manual_entries"] = entries
    st.rerun()


def _manual_documents(entries: list[str]) -> list[Document]:
    docs: list[Document] = []
    for idx, entry in enumerate(entries, start=1):
        text = entry.strip()
        if not text:
            continue
        docs.append(
            Document(
                page_content=f"Manual entry:\n{text}",
                metadata={
                    "source": f"수동 입력 #{idx}",
                    "type": "manual_entry",
                },
            )
        )
    return docs


def _render_manual_section() -> list[Document]:
    st.subheader("추가 업무 내역")
    st.caption("GitHub/Slack에 기록되지 않은 업무가 있으면 직접 입력해 주간보고 근거에 포함합니다.")

    _ensure_manual_entries()
    entries = st.session_state["manual_entries"]

    list_container = st.container(height=580) if len(entries) > 3 else st.container()
    with list_container:
        for idx, entry in enumerate(entries):
            with st.container(border=True):
                left, right = st.columns([8, 1])
                with left:
                    value = st.text_area(
                        f"업무 {idx + 1}",
                        value=entry,
                        key=f"manual_entry_{idx}",
                        placeholder="예: 4/15 Q2 OKR 워크숍 참석, 로드맵 초안 작성",
                        label_visibility="collapsed",
                        height=100,
                    )
                    st.session_state["manual_entries"][idx] = value
                with right:
                    if st.button("-", key=f"remove_manual_{idx}", use_container_width=True):
                        _remove_manual_entry(idx)

    st.button(
        "+ 업무 추가",
        on_click=_add_manual_entry,
        use_container_width=True,
        key="manual_add_button",
    )

    return _manual_documents(st.session_state["manual_entries"])


def _ensure_template_fields() -> None:
    if "template_fields" not in st.session_state:
        st.session_state["template_fields"] = list(DEFAULT_TEMPLATE_FIELDS)
    if "generated_report" not in st.session_state:
        st.session_state["generated_report"] = ""
    if "generated_report_error" not in st.session_state:
        st.session_state["generated_report_error"] = ""
    if "report_style" not in st.session_state:
        st.session_state["report_style"] = "match"


def _add_template_field() -> None:
    st.session_state["template_fields"] = [*st.session_state["template_fields"], ""]


def _remove_template_field(index: int) -> None:
    fields = list(st.session_state["template_fields"])
    if len(fields) <= 1:
        return
    fields.pop(index)
    st.session_state["template_fields"] = fields
    st.rerun()


def _render_template_builder() -> tuple[str, list, list[str], str, bool]:
    _ensure_template_fields()

    st.subheader("주간보고 양식")
    for idx, field in enumerate(st.session_state["template_fields"]):
        with st.container(border=True):
            left, right = st.columns([8, 1])
            with left:
                value = st.text_input(
                    f"항목 {idx + 1}",
                    value=field,
                    key=f"template_field_{idx}",
                    placeholder="예: 업무 내용 및 활동",
                    label_visibility="collapsed",
                )
                st.session_state["template_fields"][idx] = value
            with right:
                if st.button("-", key=f"remove_field_{idx}", use_container_width=True):
                    _remove_template_field(idx)

    st.button("+ 항목 추가", on_click=_add_template_field, use_container_width=True)

    cleaned_fields = [field.strip() for field in st.session_state["template_fields"] if field.strip()]
    template = "\n\n".join(f"{idx + 1}. {field}\n- " for idx, field in enumerate(cleaned_fields))

    example_files = st.file_uploader(
        "예시 보고서 파일 업로드",
        accept_multiple_files=True,
        type=EXAMPLE_UPLOAD_TYPES,
        help="업로드한 예시 파일은 주간보고 생성 프롬프트의 few-shot 예시로 사용됩니다.",
    )

    report_style = st.selectbox(
        "작성 옵션",
        options=["concise", "match", "detailed"],
        index=["concise", "match", "detailed"].index(st.session_state["report_style"]),
        format_func=lambda value: {
            "concise": "더 간결하게",
            "match": "예시와 비슷하게",
            "detailed": "더 풍성하게",
        }[value],
        help="예시 보고서 파일의 분량과 밀도를 기준으로 생성 결과의 간결함/풍성함을 조절합니다.",
    )
    st.session_state["report_style"] = report_style

    generate = st.button("주간보고 생성", type="primary", use_container_width=True)
    return template, example_files or [], cleaned_fields, report_style, generate


st.title("주간보고 생성기")
st.caption("GitHub 커밋, Slack 파일 기록, 직접 입력한 업무 내역을 근거로 지정한 항목 구조에 맞는 주간보고를 생성합니다.")

top_left_col, top_middle_col, top_right_col = st.columns(3, gap="large")

with top_left_col:
    github_docs = _render_github_section()

with top_middle_col:
    slack_docs = _render_slack_section()

with top_right_col:
    manual_docs = _render_manual_section()

st.divider()

bottom_left_col, bottom_right_col = st.columns(2, gap="large")

with bottom_left_col:
    template, example_files, template_fields, report_style, generate = _render_template_builder()

if generate:
    documents = [*github_docs, *slack_docs, *manual_docs]
    if not documents:
        st.error("GitHub 커밋, Slack 기록, 또는 추가 업무 내역 중 하나 이상이 필요합니다.")
        st.stop()
    if not template.strip():
        st.error("주간보고 항목을 최소 한 개 이상 입력해야 합니다.")
        st.stop()

    with bottom_right_col:
        with st.spinner("주간보고 생성을 진행 중입니다."):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    example_documents = []
                    example_paths: list[Path] = []
                    for uploaded in example_files:
                        path = Path(tmp_dir) / f"example_{uploaded.name}"
                        path.write_bytes(uploaded.getbuffer())
                        example_paths.append(path)

                    example_documents.extend(load_example_documents(example_paths))

                    result = generate_weekly_report(
                        documents=documents,
                        template=template,
                        template_fields=template_fields,
                        report_style=report_style,
                        example_documents=example_documents,
                    )
            except Exception as exc:
                error_message = _format_report_generation_error(exc)
                st.session_state["generated_report_error"] = error_message
                st.toast(error_message, icon=":material/error:")
            else:
                st.session_state["generated_report"] = str(result["report"])
                st.session_state["generated_report_error"] = ""


with bottom_right_col:
    if st.session_state.get("generated_report_error"):
        st.error(st.session_state["generated_report_error"])
    if st.session_state.get("generated_report"):
        st.subheader("생성된 주간보고")
        st.text_area("결과", value=st.session_state["generated_report"], height=420)
