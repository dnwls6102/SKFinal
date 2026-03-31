from __future__ import annotations

import html
import tempfile
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from github_integration import (
    GitHubOAuthError,
    build_login_url,
    clear_commit_cache,
    clear_saved_session,
    commit_documents,
    exchange_code_for_token,
    fetch_authenticated_user,
    fetch_user_orgs,
    fetch_user_repositories,
    fetch_weekly_commits,
    get_current_week_range,
    load_commit_cache,
    load_saved_session,
    save_commit_cache,
    save_session,
)
from loaders import load_documents
from rag_pipeline import generate_weekly_report


load_dotenv()

st.set_page_config(page_title="Weekly Report RAG", layout="wide")

DEFAULT_TEMPLATE_FIELDS = [
    "업무 내용 및 활동",
    "성공적으로 잘 수행했다고 생각하는 점",
    "스스로 부족하다고 생각하는 점/보완 계획",
]


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


def _bootstrap_saved_session() -> None:
    if st.session_state.get("github_token") and st.session_state.get("github_user"):
        return

    saved = load_saved_session()
    if not saved:
        return

    token, user = saved
    try:
        verified_user = fetch_authenticated_user(token)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in {401, 403}:
            clear_saved_session()
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

    if error:
        st.error(f"GitHub OAuth 오류: {error}")
        st.query_params.clear()
        return

    if not code or not state or st.session_state.get("github_token"):
        return

    try:
        token = exchange_code_for_token(code, state)
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
    save_session(token, user)
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


def _build_repo_groups(repos: list[dict[str, object]], orgs: list[dict[str, object]]) -> dict[str, list[str]]:
    grouped_repos: dict[str, list[str]] = {"개인": []}
    for org in orgs:
        login = str(org.get("login", "")).strip()
        if login:
            grouped_repos[f"조직: {login}"] = []

    for repo in repos:
        repo_name = str(repo["full_name"])
        owner = repo.get("owner", {})
        owner_login = str(owner.get("login", "unknown"))
        owner_type = str(owner.get("type", ""))
        group_name = f"조직: {owner_login}" if owner_type == "Organization" else "개인"
        grouped_repos.setdefault(group_name, []).append(repo_name)

    ordered = {"개인": sorted(grouped_repos.get("개인", []), key=str.lower)}
    for name in sorted((item for item in grouped_repos.keys() if item != "개인"), key=str.lower):
        ordered[name] = sorted(grouped_repos[name], key=str.lower)
    return ordered


def _render_group_selection(repos: list[dict[str, object]], orgs: list[dict[str, object]]) -> set[str]:
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
        if st.button("전체 선택", use_container_width=True):
            st.session_state["selected_repo_groups"] = set(group_names)
    with right:
        if st.button("전체 해제", use_container_width=True):
            st.session_state["selected_repo_groups"] = set()

    selected_groups = st.session_state["selected_repo_groups"]
    with st.expander("개인/조직 선택", expanded=False):
        for group_name in group_names:
            checked = group_name in selected_groups
            if st.checkbox(group_name, value=checked, key=f"group_checkbox::{group_name}"):
                selected_groups.add(group_name)
            else:
                selected_groups.discard(group_name)

    st.session_state["selected_repo_groups"] = selected_groups
    return {
        repo_name
        for group_name in selected_groups
        for repo_name in grouped_repos[group_name]
    }


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
    components.html(html_block, height=440, scrolling=False)


def _render_github_section():
    st.subheader("GitHub 연동")
    _bootstrap_saved_session()
    _handle_github_oauth_callback()

    token = st.session_state.get("github_token")
    user = st.session_state.get("github_user")

    if not token or not user:
        try:
            login_url = build_login_url()
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
        if st.button("GitHub 연결 해제", use_container_width=True):
            _clear_github_session_state()
            clear_saved_session()
            clear_commit_cache()
            st.rerun()

    try:
        orgs = _load_orgs(token)
        repos = _load_repositories(token)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in {401, 403}:
            clear_saved_session()
            clear_commit_cache()
            _clear_github_session_state()
            st.error("저장된 GitHub 로그인 정보가 만료되었습니다. 다시 로그인해야 합니다.")
            return []
        st.error(f"GitHub 데이터 조회 중 오류가 발생했습니다: {exc}")
        return []
    except Exception as exc:
        st.error(f"GitHub 데이터 조회 중 오류가 발생했습니다: {exc}")
        return []

    selected_repos = _render_group_selection(repos, orgs)

    week_start, week_end = get_current_week_range()
    week_key = week_start.strftime("%Y-%m-%d")
    st.caption(f"조회 범위: {week_start:%Y-%m-%d %H:%M} ~ {week_end:%Y-%m-%d %H:%M} (Asia/Seoul 기준)")

    refresh = st.button("이번 주 커밋 새로고침", use_container_width=True)
    cache_key_changed = st.session_state.get("weekly_commit_cache_key") != week_key
    if cache_key_changed:
        st.session_state.pop("all_weekly_commits", None)
        st.session_state["weekly_commit_cache_key"] = week_key

    if not refresh and "all_weekly_commits" not in st.session_state:
        cached_commits = load_commit_cache(str(user["login"]), week_key)
        if cached_commits is not None:
            st.session_state["all_weekly_commits"] = cached_commits

    if refresh or "all_weekly_commits" not in st.session_state:
        with st.spinner("GitHub에서 이번 주 커밋 메시지를 가져오는 중입니다."):
            try:
                all_commits = fetch_weekly_commits(token, str(user["login"]))
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in {401, 403}:
                    clear_saved_session()
                    clear_commit_cache()
                    _clear_github_session_state()
                    st.error("저장된 GitHub 로그인 정보가 만료되었습니다. 다시 로그인해야 합니다.")
                    return []
                st.error(f"커밋 조회 중 오류가 발생했습니다: {exc}")
                return []
            except Exception as exc:
                st.error(f"커밋 조회 중 오류가 발생했습니다: {exc}")
                return []

            st.session_state["all_weekly_commits"] = all_commits
            save_commit_cache(str(user["login"]), week_key, all_commits)

    all_commits = st.session_state.get("all_weekly_commits", [])
    commits = [commit for commit in all_commits if commit.repo_full_name in selected_repos]
    st.session_state["weekly_commits"] = commits

    st.write(f"이번 주 커밋 수: {len(commits)}")
    if not commits:
        st.info("선택된 그룹 기준 이번 주 커밋이 없습니다.")
        return []

    _render_commit_list(commits)
    return commit_documents(commits)


def _ensure_template_fields() -> None:
    if "template_fields" not in st.session_state:
        st.session_state["template_fields"] = list(DEFAULT_TEMPLATE_FIELDS)


def _add_template_field() -> None:
    st.session_state["template_fields"] = [*st.session_state["template_fields"], ""]


def _remove_template_field(index: int) -> None:
    fields = list(st.session_state["template_fields"])
    if len(fields) <= 1:
        return
    fields.pop(index)
    st.session_state["template_fields"] = fields
    st.rerun()


def _render_template_builder() -> tuple[str, list, list[str]]:
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
        type=["xlsx", "pdf", "docx", "txt", "md"],
        help="업로드한 예시 파일은 주간보고 생성 프롬프트의 few-shot 예시로 사용됩니다.",
    )
    return template, example_files or [], cleaned_fields


st.title("주간보고 생성기")
st.caption("GitHub 커밋을 근거로, 지정한 항목 구조에 맞는 주간보고를 생성합니다.")

left_col, right_col = st.columns([1.2, 1.0], gap="large")

with left_col:
    github_docs = _render_github_section()

with right_col:
    template, example_files, template_fields = _render_template_builder()

generate = st.button("주간보고 생성", type="primary", use_container_width=True)

if generate:
    if not github_docs:
        st.error("GitHub 커밋 데이터가 필요합니다.")
        st.stop()
    if not template.strip():
        st.error("주간보고 항목을 최소 한 개 이상 입력해야 합니다.")
        st.stop()

    with st.spinner("주간보고 생성을 진행 중입니다."):
        with tempfile.TemporaryDirectory() as tmp_dir:
            documents = list(github_docs)
            example_documents = []

            example_paths: list[Path] = []
            for uploaded in example_files:
                path = Path(tmp_dir) / f"example_{uploaded.name}"
                path.write_bytes(uploaded.getbuffer())
                example_paths.append(path)

            example_documents.extend(load_documents(example_paths))

            result = generate_weekly_report(
                documents=documents,
                template=template,
                template_fields=template_fields,
                example_documents=example_documents,
            )

    st.subheader("생성된 주간보고")
    st.text_area("결과", value=result["report"], height=420, disabled=True)

    st.subheader("구조화 출력")
    st.json(result["structured_report"])

    st.subheader("RAG 검색 질의")
    for query in result["queries"]:
        st.write(f"- {query}")

    st.subheader("참고한 근거")
    for idx, doc in enumerate(result["retrieved_docs"], start=1):
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page")
        header = f"{idx}. {source}" + (f" / page {page}" if page else "")
        with st.expander(header):
            st.write(doc.page_content)
