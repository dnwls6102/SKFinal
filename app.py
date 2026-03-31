from __future__ import annotations

import tempfile
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

from github_integration import (
    GitHubOAuthError,
    build_login_url,
    clear_saved_session,
    commit_documents,
    exchange_code_for_token,
    fetch_authenticated_user,
    fetch_user_repositories,
    fetch_weekly_commits,
    get_current_week_range,
    load_saved_session,
    save_session,
)
from loaders import load_documents
from rag_pipeline import generate_weekly_report


load_dotenv()

st.set_page_config(
    page_title="Weekly Report RAG",
    layout="wide",
)


def _clear_github_session_state() -> None:
    for key in (
        "github_token",
        "github_user",
        "github_repos",
        "weekly_commits",
        "all_weekly_commits",
        "selected_repo_groups",
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
        # 네트워크가 잠시 막혀도 기존 저장 세션은 유지한다.
        verified_user = user

    st.session_state["github_token"] = token
    st.session_state["github_user"] = verified_user or user


def _handle_github_oauth_callback() -> None:
    query_params = st.query_params
    code = query_params.get("code")
    state = query_params.get("state")
    error = query_params.get("error")

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
    st.session_state.pop("github_repos", None)
    st.session_state.pop("weekly_commits", None)
    st.session_state.pop("all_weekly_commits", None)
    save_session(token, user)
    st.query_params.clear()
    st.rerun()


def _load_repositories(token: str) -> list[dict[str, object]]:
    repos = st.session_state.get("github_repos")
    if repos is None:
        repos = fetch_user_repositories(token)
        st.session_state["github_repos"] = repos
    return repos


def _build_repo_groups(repos: list[dict[str, object]], user_login: str) -> dict[str, list[str]]:
    grouped_repos: dict[str, list[str]] = {}
    for repo in repos:
        repo_name = str(repo["full_name"])
        owner = repo.get("owner", {})
        owner_login = str(owner.get("login", "unknown"))
        owner_type = str(owner.get("type", ""))

        if owner_type == "Organization":
            group_name = f"조직: {owner_login}"
        elif owner_login.lower() == user_login.lower():
            group_name = "개인"
        else:
            group_name = f"개인/기타: {owner_login}"

        grouped_repos.setdefault(group_name, []).append(repo_name)
    return dict(sorted(grouped_repos.items(), key=lambda item: item[0].lower()))


def _render_group_selection(repos: list[dict[str, object]]) -> tuple[set[str], dict[str, list[str]]]:
    st.write(f"조회 가능한 레포 수: {len(repos)}")
    if not repos:
        st.info("조회 가능한 레포가 없습니다.")
        return set(), {}

    user_login = str(st.session_state.get("github_user", {}).get("login", ""))
    grouped_repos = _build_repo_groups(repos, user_login)
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
    with st.expander("대상 그룹 선택", expanded=False):
        for group_name in group_names:
            repo_count = len(grouped_repos[group_name])
            checked = group_name in selected_groups
            new_value = st.checkbox(
                f"{group_name} ({repo_count})",
                value=checked,
                key=f"group_checkbox::{group_name}",
            )
            if new_value:
                selected_groups.add(group_name)
            else:
                selected_groups.discard(group_name)

    st.session_state["selected_repo_groups"] = selected_groups
    selected_repos = {
        repo_name
        for group_name in selected_groups
        for repo_name in grouped_repos[group_name]
    }

    st.caption(f"선택된 그룹: {len(selected_groups)} / {len(group_names)}")
    st.caption(f"포함된 레포: {len(selected_repos)} / {sum(len(v) for v in grouped_repos.values())}")
    return selected_repos, grouped_repos


def _filter_commits_by_selected_repos(commits, selected_repos: set[str]):
    return [commit for commit in commits if commit.repo_full_name in selected_repos]


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
            st.rerun()

    try:
        repos = _load_repositories(token)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in {401, 403}:
            clear_saved_session()
            _clear_github_session_state()
            st.error("저장된 GitHub 로그인 정보가 만료되었습니다. 다시 로그인해야 합니다.")
            return []
        st.error(f"레포 목록 조회 중 오류가 발생했습니다: {exc}")
        return []
    except Exception as exc:
        st.error(f"레포 목록 조회 중 오류가 발생했습니다: {exc}")
        return []

    selected_repos, _ = _render_group_selection(repos)

    week_start, week_end = get_current_week_range()
    st.caption(
        f"조회 범위: {week_start.strftime('%Y-%m-%d %H:%M')} ~ {week_end.strftime('%Y-%m-%d %H:%M')} (Asia/Seoul 기준)"
    )

    refresh = st.button("이번 주 커밋 새로고침", use_container_width=True)
    if refresh or "all_weekly_commits" not in st.session_state:
        with st.spinner("GitHub에서 이번 주 커밋 메시지를 가져오는 중입니다."):
            try:
                all_commits = fetch_weekly_commits(token, str(user["login"]))
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in {401, 403}:
                    clear_saved_session()
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
    commits = _filter_commits_by_selected_repos(all_commits, selected_repos)
    st.session_state["weekly_commits"] = commits
    st.write(f"이번 주 커밋 수: {len(commits)}")

    if not commits:
        st.info("선택된 그룹 기준 이번 주 커밋이 없습니다.")
        return []

    for idx, commit in enumerate(commits, start=1):
        title = f"{idx}. {commit.repo_full_name} / {commit.author_date[:10]}"
        with st.expander(title):
            st.code(commit.message, language="text")
            st.caption(commit.url)

    return commit_documents(commits)


st.title("주간보고 생성기")
st.caption("업로드한 문서와 GitHub 커밋에서 근거를 찾아, 지정한 양식에 맞는 주간보고를 생성합니다.")

github_docs = _render_github_section()
st.divider()

template = st.text_area(
    "주간보고 양식",
    height=220,
    value=(
        "1. 이번 주 주요 업무\n"
        "- \n\n"
        "2. 산출물 및 진행 결과\n"
        "- \n\n"
        "3. 이슈 및 리스크\n"
        "- \n\n"
        "4. 다음 주 계획\n"
        "- "
    ),
)

user_context = st.text_area(
    "추가 설명",
    height=100,
    placeholder="프로젝트명, 팀명, 강조해야 할 포인트, 제외할 내용 등을 적으세요.",
)

uploaded_files = st.file_uploader(
    "문서/코드 업로드",
    accept_multiple_files=True,
    type=[
        "pdf",
        "docx",
        "txt",
        "md",
        "py",
        "js",
        "ts",
        "tsx",
        "jsx",
        "java",
        "go",
        "rs",
        "sql",
        "json",
        "yaml",
        "yml",
        "css",
        "html",
        "ps1",
    ],
)

generate = st.button("주간보고 생성", type="primary", use_container_width=True)

if generate:
    if not uploaded_files and not github_docs:
        st.error("최소 한 개 이상의 문서/코드 파일 또는 GitHub 커밋 데이터가 필요합니다.")
        st.stop()
    if not template.strip():
        st.error("주간보고 양식을 입력해야 합니다.")
        st.stop()

    with st.spinner("파일 분석과 주간보고 생성을 진행 중입니다."):
        with tempfile.TemporaryDirectory() as tmp_dir:
            documents = list(github_docs)
            saved_paths: list[Path] = []
            for uploaded in uploaded_files or []:
                path = Path(tmp_dir) / uploaded.name
                path.write_bytes(uploaded.getbuffer())
                saved_paths.append(path)

            documents.extend(load_documents(saved_paths))
            if not documents:
                st.error("지원되는 텍스트를 추출하지 못했습니다. 파일 형식을 확인하세요.")
                st.stop()

            result = generate_weekly_report(
                documents=documents,
                template=template,
                user_context=user_context,
            )

    st.subheader("생성된 주간보고")
    st.text_area("결과", value=result["report"], height=420)

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
