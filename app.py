from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from loaders import load_documents
from rag_pipeline import generate_weekly_report


load_dotenv()

st.set_page_config(
    page_title="Weekly Report RAG",
    layout="wide",
)

st.title("주간보고 생성기")
st.caption("업로드한 문서와 코드에서 근거를 찾아, 지정한 양식에 맞는 주간보고를 생성합니다.")

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
    if not uploaded_files:
        st.error("최소 한 개 이상의 문서 또는 코드 파일을 업로드해야 합니다.")
        st.stop()
    if not template.strip():
        st.error("주간보고 양식을 입력해야 합니다.")
        st.stop()

    with st.spinner("파일 분석과 주간보고 생성을 진행 중입니다."):
        with tempfile.TemporaryDirectory() as tmp_dir:
            saved_paths: list[Path] = []
            for uploaded in uploaded_files:
                path = Path(tmp_dir) / uploaded.name
                path.write_bytes(uploaded.getbuffer())
                saved_paths.append(path)

            documents = load_documents(saved_paths)
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
