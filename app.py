from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from github_integration import (
    GitHubOAuthError,
    build_login_url,
    commit_documents,
    exchange_code_for_token,
    fetch_authenticated_user,
    fetch_weekly_commits,
    get_current_week_range,
)
from loaders import load_documents
from rag_pipeline import generate_weekly_report


load_dotenv()

st.set_page_config(
    page_title="Weekly Report RAG",
    layout="wide",
)

st.title("주간보고 생성기")
st.caption("업로드한 문서와 GitHub 커밋에서 근거를 찾아, 지정한 양식에 맞는 주간보고를 생성합니다.")


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
    st.query_params.clear()
    st.rerun()


def _render_github_section():
    st.subheader("GitHub 연동")
    _handle_github_oauth_callback()

    token = st.session_state.get("github_token")
    user = st.session_state.get("github_user")

    if not token or not user:
        try:
            login_url = build_login_url()
            st.link_button("GitHub 로그인", login_url, use_container_width=True)
            st.caption("로그인 후 접근 가능한 모든 레포에서 이번 주 커밋 메시지를 자동으로 수집합니다.")
        except GitHubOAuthError as exc:
            st.warning(str(exc))
            st.caption("`.env`에 `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`를 설정해야 합니다.")
        return []

    left, right = st.columns([3, 1])
    with left:
        st.success(f"GitHub 연결됨: {user.get('login')}")
    with right:
        if st.button("GitHub 연결 해제", use_container_width=True):
            st.session_state.pop("github_token", None)
            st.session_state.pop("github_user", None)
            st.session_state.pop("weekly_commits", None)
            st.rerun()

    week_start, week_end = get_current_week_range()
    st.caption(
        f"조회 범위: {week_start.strftime('%Y-%m-%d %H:%M')} ~ {week_end.strftime('%Y-%m-%d %H:%M')} (Asia/Seoul 기준)"
    )

    refresh = st.button("이번 주 커밋 새로고침", use_container_width=True)
    if refresh or "weekly_commits" not in st.session_state:
        with st.spinner("GitHub에서 이번 주 커밋 메시지를 가져오는 중입니다."):
            try:
                commits = fetch_weekly_commits(token, str(user["login"]))
            except Exception as exc:
                st.error(f"커밋 조회 중 오류가 발생했습니다: {exc}")
                return []
            st.session_state["weekly_commits"] = commits

    commits = st.session_state.get("weekly_commits", [])
    st.write(f"이번 주 커밋 수: {len(commits)}")

    if not commits:
        st.info("이번 주 커밋이 없습니다.")
        return []

    for idx, commit in enumerate(commits, start=1):
        title = f"{idx}. {commit.repo_full_name} / {commit.author_date[:10]}"
        with st.expander(title):
            st.code(commit.message, language="text")
            st.caption(commit.url)

    return commit_documents(commits)


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
