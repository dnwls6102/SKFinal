# Weekly Report Studio

GitHub commit history and Slack shared files/messages are collected as evidence and turned into a grounded weekly report.

## Stack

- `app/`, `src/components/`: Next.js frontend on port `8501`
- `backend_api.py`: FastAPI backend for OAuth, source loading, and report generation
- `github_integration.py`: GitHub OAuth and weekly commit collection
- `slack_integration.py`: Slack OAuth and weekly shared file/message collection
- `rag_pipeline.py`: LangGraph-based grounded report generation pipeline
- `loaders.py`: PDF, DOCX, XLSX, text example file loaders

## Install

Python dependencies:

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

Frontend dependencies:

```powershell
npm install
```

## Environment

Set values in `.env`.

```env
GOOGLE_API_KEY=your_google_api_key
GEMINI_MODEL=gemini-3-flash-preview
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GITHUB_REDIRECT_URI=http://localhost:8501
SLACK_CLIENT_ID=your_slack_client_id
SLACK_CLIENT_SECRET=your_slack_client_secret
SLACK_REDIRECT_URI=https://your-ngrok-domain.ngrok-free.dev
```

OAuth redirect targets should continue pointing to the frontend origin on port `8501`. The frontend handles the callback query string and sends the code/state to FastAPI.

## Run

Start the FastAPI backend on port `8000`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend_api:app --reload --port 8000
```

Start the Next.js frontend on port `8501`:

```powershell
npm run dev
```

## Notes

- The frontend proxies `/api/backend/*` to `http://127.0.0.1:8000/*`, so ngrok can stay pointed at the frontend port `8501`.
- GitHub and Slack sessions are still persisted in the existing local cache/session JSON files.
- The previous Streamlit app remains in `app.py` for reference, but the active UI is now Next.js.
