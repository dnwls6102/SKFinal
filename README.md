# Weekly Report RAG

사용자가 이번 주에 작업한 문서와 코드를 업로드하면, 업로드 자료를 RAG해서 지정한 양식에 맞는 주간보고를 생성하는 Streamlit 프로젝트입니다.

## 구성

- `app.py`: Streamlit UI
- `loaders.py`: PDF, DOCX, 코드/텍스트 파일 로더
- `rag_pipeline.py`: LangGraph 기반 질의 생성 -> 검색 -> 보고서 작성 파이프라인

## 설치

```powershell
python -m pip install --user -r requirements.txt
copy .env.example .env
```

`.env` 또는 시스템 환경변수에 `GOOGLE_API_KEY`를 설정해야 합니다.

## 실행

```powershell
streamlit run app.py
```

## 동작 방식

1. 사용자가 문서 또는 코드 파일을 업로드합니다.
2. 파일 내용을 텍스트로 추출하고 chunk 단위로 분할합니다.
3. LangGraph가 주간보고 양식 기반 검색 질의를 생성합니다.
4. BM25 기반으로 관련 chunk를 검색합니다.
5. Gemini가 검색 근거를 바탕으로 주간보고를 작성합니다.

## 지원 파일

- 문서: `pdf`, `docx`, `txt`, `md`
- 코드/설정: `py`, `js`, `ts`, `tsx`, `jsx`, `java`, `go`, `rs`, `sql`, `json`, `yaml`, `yml`, `css`, `html`, `ps1`
