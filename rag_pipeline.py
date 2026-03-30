from __future__ import annotations

import os
from typing import TypedDict

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import END, StateGraph


class ReportState(TypedDict, total=False):
    template: str
    user_context: str
    documents: list[Document]
    chunks: list[Document]
    queries: list[str]
    retrieved_docs: list[Document]
    report: str


def _get_llm(api_key: str | None = None, model: str | None = None) -> ChatGoogleGenerativeAI:
    resolved_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not resolved_key:
        raise ValueError("GOOGLE_API_KEY가 필요합니다.")
    return ChatGoogleGenerativeAI(
        google_api_key=resolved_key,
        model=model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-09-2025"),
        temperature=0.2,
    )


def build_chunks(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=180,
        separators=["\nclass ", "\ndef ", "\n## ", "\n# ", "\n\n", "\n", " ", ""],
    )
    return splitter.split_documents(documents)


def _plan_queries(state: ReportState) -> ReportState:
    llm = _get_llm()
    message = HumanMessage(
        content=(
            "아래 정보를 바탕으로 주간보고 작성을 위한 검색 질의 5개를 만들어라.\n"
            "조건:\n"
            "- 각 질의는 작업 내용, 결과물, 이슈, 다음 액션을 찾는 데 도움 되어야 한다.\n"
            "- 한 줄에 하나씩 출력하라.\n\n"
            f"[보고 양식]\n{state['template']}\n\n"
            f"[추가 설명]\n{state.get('user_context', '')}"
        )
    )
    response = llm.invoke(
        [
            SystemMessage(content="너는 주간보고 작성을 위한 정보 수집 플래너다."),
            message,
        ]
    )
    queries = [line.strip("- ").strip() for line in response.content.splitlines() if line.strip()]
    return {"queries": queries[:5]}


def _retrieve(state: ReportState) -> ReportState:
    chunks = state["chunks"]
    retriever = BM25Retriever.from_documents(chunks)
    retriever.k = 8

    seen: set[tuple[str, str]] = set()
    retrieved_docs: list[Document] = []
    for query in state["queries"]:
        for doc in retriever.invoke(query):
            key = (doc.metadata.get("source", ""), doc.page_content)
            if key in seen:
                continue
            seen.add(key)
            retrieved_docs.append(doc)

    if not retrieved_docs:
        retrieved_docs = chunks[:8]
    return {"retrieved_docs": retrieved_docs}


def _draft_report(state: ReportState) -> ReportState:
    llm = _get_llm()
    evidence = []
    for idx, doc in enumerate(state["retrieved_docs"], start=1):
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page")
        location = f"{source} p.{page}" if page else source
        evidence.append(f"[근거 {idx}] ({location})\n{doc.page_content}")

    prompt = HumanMessage(
        content=(
            "다음 자료를 근거로 주간보고를 작성하라.\n"
            "요구사항:\n"
            "- 반드시 사용자가 준 양식을 우선해서 따른다.\n"
            "- 업로드 자료에 없는 내용은 추측하지 말고, 필요한 경우 '확인 필요'라고 표시한다.\n"
            "- 보고서는 바로 제출 가능한 톤으로 한국어로 작성한다.\n"
            "- 작업 요약, 산출물, 이슈/리스크, 다음 주 계획이 드러나야 한다.\n\n"
            f"[주간보고 양식]\n{state['template']}\n\n"
            f"[사용자 추가 설명]\n{state.get('user_context', '')}\n\n"
            f"[검색 질의]\n" + "\n".join(state["queries"]) + "\n\n"
            f"[근거 문서]\n" + "\n\n".join(evidence)
        )
    )
    response = llm.invoke(
        [
            SystemMessage(
                content="너는 업무 문서 작성에 강한 프로젝트 어시스턴트다. 근거 기반으로 간결하고 명확한 주간보고를 작성한다."
            ),
            prompt,
        ]
    )
    return {"report": response.content}


def build_workflow():
    graph = StateGraph(ReportState)
    graph.add_node("plan_queries", _plan_queries)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("draft_report", _draft_report)

    graph.set_entry_point("plan_queries")
    graph.add_edge("plan_queries", "retrieve")
    graph.add_edge("retrieve", "draft_report")
    graph.add_edge("draft_report", END)
    return graph.compile()


def generate_weekly_report(
    documents: list[Document],
    template: str,
    user_context: str = "",
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, object]:
    chunks = build_chunks(documents)
    workflow = build_workflow()

    original_api_key = os.getenv("GOOGLE_API_KEY")
    original_model = os.getenv("GEMINI_MODEL")
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
    if model:
        os.environ["GEMINI_MODEL"] = model

    try:
        result = workflow.invoke(
            {
                "template": template,
                "user_context": user_context,
                "documents": documents,
                "chunks": chunks,
            }
        )
    finally:
        if api_key is not None:
            if original_api_key is None:
                os.environ.pop("GOOGLE_API_KEY", None)
            else:
                os.environ["GOOGLE_API_KEY"] = original_api_key
        if model is not None:
            if original_model is None:
                os.environ.pop("GEMINI_MODEL", None)
            else:
                os.environ["GEMINI_MODEL"] = original_model

    return {
        "report": result["report"],
        "queries": result["queries"],
        "chunks": chunks,
        "retrieved_docs": result["retrieved_docs"],
    }
