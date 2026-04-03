from __future__ import annotations

import base64
import os
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from loaders import load_documents


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EXAMPLE_UPLOAD_TYPES = ["xlsx", "pdf", "docx", "txt", "md", "png", "jpg", "jpeg", "webp"]


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
                if text:
                    parts.append(str(text))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def _get_llm(api_key: str | None = None, model: str | None = None) -> ChatGoogleGenerativeAI:
    resolved_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not resolved_key:
        raise ValueError("GOOGLE_API_KEY가 필요합니다.")

    return ChatGoogleGenerativeAI(
        google_api_key=resolved_key,
        model=model or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
        temperature=0.0,
    )


def _ocr_image_document(path: Path, api_key: str | None = None, model: str | None = None) -> Document | None:
    suffix = path.suffix.lower()
    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix)
    if not mime_type:
        return None

    image_bytes = path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    llm = _get_llm(api_key=api_key, model=model)
    response = llm.invoke(
        [
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "이 이미지는 주간보고 예시 문서 스크린샷이다. "
                            "이미지 안의 텍스트를 최대한 정확히 추출하라. "
                            "표 구조와 줄바꿈을 가능한 한 유지하고, 설명이나 해설은 추가하지 말라. "
                            "읽을 수 없는 부분은 억지로 추측하지 말고 생략하라."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:{mime_type};base64,{image_b64}",
                    },
                ]
            )
        ]
    )
    text = _message_to_text(response.content)
    if not text.strip():
        return None
    return Document(
        page_content=text,
        metadata={"source": path.name, "type": "image_ocr", "extension": suffix},
    )


def load_example_documents(
    paths: list[Path],
    api_key: str | None = None,
    model: str | None = None,
) -> list[Document]:
    normal_paths = [path for path in paths if path.suffix.lower() not in IMAGE_EXTENSIONS]
    image_paths = [path for path in paths if path.suffix.lower() in IMAGE_EXTENSIONS]

    documents = load_documents(normal_paths)
    for path in image_paths:
        doc = _ocr_image_document(path, api_key=api_key, model=model)
        if doc is not None:
            documents.append(doc)
    return documents
