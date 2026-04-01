from __future__ import annotations

import json
import os
import re
from typing import TypedDict

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import END, StateGraph


class ReportState(TypedDict, total=False):
    template: str
    template_fields: list[str]
    report_style: str
    documents: list[Document]
    example_documents: list[Document]
    chunks: list[Document]
    queries: list[str]
    retrieved_docs: list[Document]
    structured_report: dict[str, str]
    report: str


STYLE_INSTRUCTIONS = {
    "concise": (
        "예시 보고서의 문체와 톤은 그대로 유지하되, 분량만 더 간결하게 줄인다.\n"
        "각 항목은 핵심 사실과 결과 중심으로 짧고 명확하게 정리한다."
    ),
    "match": (
        "예시 보고서의 문체, 어휘 선택, 문장 길이, 불릿 스타일, 서술 밀도를 최대한 비슷하게 맞춘다.\n"
        "예시가 가진 말투와 정리 방식을 그대로 따른다."
    ),
    "detailed": (
        "예시 보고서의 문체와 톤은 그대로 유지하되, 내용만 더 풍성하고 상세하게 작성한다.\n"
        "가능하면 진행 맥락, 작업 내용, 결과, 의미를 조금 더 구체적으로 덧붙인다."
    ),
}


def _strip_evidence_markers(text: str) -> str:
    cleaned = re.sub(r"\s*\((근거|출처)[^)]+\)", "", text)
    cleaned = re.sub(r"\s*\[(근거|출처)[^\]]+\]", "", cleaned)
    cleaned = re.sub(r"(?im)^\s*출처\s*:\s*.*$", "", cleaned)
    return "\n".join(line.rstrip() for line in cleaned.splitlines()).strip()


def _message_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "text", None)
                parts.append(str(text) if text else str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def _get_llm(api_key: str | None = None, model: str | None = None) -> ChatGoogleGenerativeAI:
    resolved_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not resolved_key:
        raise ValueError("GOOGLE_API_KEY가 필요합니다.")

    return ChatGoogleGenerativeAI(
        google_api_key=resolved_key,
        model=model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
        temperature=0.05,
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
    field_lines = "\n".join(f"- {field}" for field in state.get("template_fields", []))
    response = llm.invoke(
        [
            SystemMessage(content="당신은 주간보고 작성을 위한 정보 수집 플래너다."),
            HumanMessage(
                content=(
                    "아래 정보를 바탕으로 주간보고 작성을 위한 검색 질의 5개를 만들어라.\n"
                    "조건:\n"
                    "- 작업 내용, 결과물, 이슈, 다음 액션을 찾는 데 도움이 되어야 한다.\n"
                    "- 한 줄에 하나씩 출력한다.\n\n"
                    f"[주간보고 양식]\n{state['template']}\n\n"
                    f"[필수 항목]\n{field_lines}"
                )
            ),
        ]
    )
    response_text = _message_to_text(response.content)
    queries = [line.strip("- ").strip() for line in response_text.splitlines() if line.strip()]
    return {"queries": queries[:5]}


def _build_example_block(example_documents: list[Document]) -> str:
    if not example_documents:
        return ""

    rendered: list[str] = []
    for idx, doc in enumerate(example_documents[:3], start=1):
        source = doc.metadata.get("source", "unknown")
        sheet = doc.metadata.get("sheet")
        location = f"{source} / {sheet}" if sheet else source
        content = doc.page_content.strip()
        if len(content) > 2500:
            content = content[:2500] + "\n..."
        rendered.append(f"[예시 {idx}] ({location})\n{content}")
    return "\n\n".join(rendered)


def _retrieve(state: ReportState) -> ReportState:
    retriever = BM25Retriever.from_documents(state["chunks"])
    retriever.k = 8

    seen: set[tuple[str, str]] = set()
    retrieved_docs: list[Document] = []
    for query in state["queries"]:
        for doc in retriever.invoke(query):
            key = (str(doc.metadata.get("source", "")), doc.page_content)
            if key in seen:
                continue
            seen.add(key)
            retrieved_docs.append(doc)

    if not retrieved_docs:
        retrieved_docs = state["chunks"][:8]
    return {"retrieved_docs": retrieved_docs}


def _draft_report(state: ReportState) -> ReportState:
    llm = _get_llm()

    evidence: list[str] = []
    for idx, doc in enumerate(state["retrieved_docs"], start=1):
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page")
        location = f"{source} p.{page}" if page else source
        evidence.append(f"[근거 {idx}] ({location})\n{doc.page_content}")

    fields = state.get("template_fields", [])
    report_style = state.get("report_style", "match")
    examples = _build_example_block(state.get("example_documents", []))
    style_instruction = STYLE_INSTRUCTIONS.get(report_style, STYLE_INSTRUCTIONS["match"])

    example_section = f"[예시 보고서]\n{examples}\n\n" if examples else ""
    query_section = "[검색 질의]\n" + "\n".join(state["queries"]) + "\n\n"
    evidence_section = "[근거 문서]\n" + "\n\n".join(evidence)
    field_section = "[필수 항목]\n" + "\n".join(f"- {field}" for field in fields) + "\n\n"
    style_section = f"[작성 옵션]\n{style_instruction}\n\n"

    prompt_content = (
        "다음 자료를 근거로 주간보고를 작성하라.\n"
        "요구사항:\n"
        "- 반드시 사용자가 준 항목명을 그대로 사용한다.\n"
        "- 근거 문서에 없는 내용은 추측하지 말고, 필요하면 '확인 필요'라고 쓴다.\n"
        "- 예시 보고서가 있으면 그 예시를 단순 참고가 아니라 문체 기준본으로 사용한다.\n"
        "- 예시의 어휘, 문장 길이, 불릿 형태, 문장 종결 방식, 서술 밀도를 최대한 그대로 따른다.\n"
        "- 내용만 이번 주 근거에 맞게 바꾸고, 서술 스타일은 예시에 최대한 가깝게 유지한다.\n"
        "- 작성 옵션은 예시 문체를 유지한 채 분량만 조절하는 용도로만 사용한다.\n"
        "- 답변 본문에 출처, 근거 번호, 괄호 메모를 쓰지 않는다.\n"
        "- '(근거 1)', '[근거 2]', '출처:' 같은 표기를 절대 포함하지 않는다.\n\n"
        f"[주간보고 양식]\n{state['template']}\n\n"
        f"{field_section}"
        f"{style_section}"
        f"{example_section}"
        f"{query_section}"
        f"{evidence_section}\n\n"
        "출력 형식:\n"
        "- 반드시 JSON 객체 하나만 출력한다.\n"
        "- key는 필수 항목명을 그대로 사용한다.\n"
        "- value는 각 항목에 들어갈 문자열이다.\n"
        "- JSON 바깥의 설명, 마크다운, 코드블록은 출력하지 않는다."
    )

    response = llm.invoke(
        [
            SystemMessage(
                content=(
                    "당신은 근거 기반으로 주간보고를 작성하는 업무 문서 작성 어시스턴트다. "
                    "예시 보고서가 주어지면 그 문체와 정리 방식을 매우 엄격하게 모방한다."
                )
            ),
            HumanMessage(content=prompt_content),
        ]
    )
    content = _message_to_text(response.content).strip()

    try:
        structured_report = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("모델이 JSON 형식으로 응답하지 않았습니다.")
        structured_report = json.loads(content[start : end + 1])

    normalized: dict[str, str] = {}
    rendered_sections: list[str] = []
    for field in fields:
        value = structured_report.get(field, "확인 필요")
        text = "\n".join(str(item) for item in value) if isinstance(value, list) else str(value)
        text = _strip_evidence_markers(text)
        normalized[field] = text
        rendered_sections.append(f"{field}\n{text}")

    return {
        "structured_report": normalized,
        "report": "\n\n".join(rendered_sections),
    }


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
    template_fields: list[str],
    report_style: str = "match",
    example_documents: list[Document] | None = None,
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
                "template_fields": template_fields,
                "report_style": report_style,
                "documents": documents,
                "example_documents": example_documents or [],
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
        "structured_report": result["structured_report"],
        "queries": result["queries"],
        "chunks": chunks,
        "retrieved_docs": result["retrieved_docs"],
    }
