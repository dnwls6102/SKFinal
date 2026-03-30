# Weekly Report RAG

업로드한 문서와 GitHub 커밋 메시지를 바탕으로, 지정한 양식에 맞는 주간보고를 생성하는 Streamlit 프로젝트입니다.

## 구성

- `app.py`: Streamlit UI, GitHub OAuth 로그인, 주간보고 생성 진입점
- `github_integration.py`: GitHub OAuth 및 이번 주 커밋 메시지 수집
- `loaders.py`: PDF, DOCX, 코드/텍스트 파일 로더
- `rag_pipeline.py`: LangGraph 기반 질의 생성 -> 검색 -> 보고서 작성 파이프라인

## 설치

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

## 환경변수

`.env`에 아래 값을 설정합니다.

```env
GOOGLE_API_KEY=your_google_api_key
GEMINI_MODEL=gemini-3-flash-preview
GITHUB_CLIENT_ID=your_github_oauth_client_id
GITHUB_CLIENT_SECRET=your_github_oauth_client_secret
GITHUB_REDIRECT_URI=http://localhost:8501
```

## GitHub OAuth 설정

GitHub OAuth App의 callback URL을 `GITHUB_REDIRECT_URI`와 동일하게 맞춰야 합니다.
로컬 기본값은 `http://localhost:8501`입니다.

현재 구현은 GitHub OAuth 로그인 후 `사용자가 접근 가능한 레포`를 조회하고, 각 레포에서 이번 주 월요일 00:00부터 현재 시각까지의 커밋 메시지를 가져옵니다.
시간 기준은 `Asia/Seoul`입니다.

## 실행

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

## 참고

- 비공개 레포까지 포함하려면 GitHub OAuth App 권한과 계정 접근 권한이 필요합니다.
- 현재 OAuth scope는 `read:user repo`를 사용합니다.
