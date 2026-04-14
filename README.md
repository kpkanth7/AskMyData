# askmydata

askmydata is a full-stack dashboard and chat hybrid for asking natural-language questions over uploaded CSV/XLSX files and connected SQL databases.

It is cloud-first and local-second:

- Primary LLM provider: Cerebras
- Default cloud model: `qwen-3-235b-a22b-instruct-2507`
- Optional local fallback provider: Ollama
- Local fallback model: configurable with `OLLAMA_MODEL`

## What It Supports

- CSV and XLSX uploads
- SQLite, MySQL, and PostgreSQL connections
- Connection strings as the canonical backend method
- Optional manual SQL connection fields in the UI
- A hard cap of 5 uploaded files per workspace/session
- A hard cap of 10 MB per uploaded file
- Per-upload-batch light cleaning prompt
- Separate result sections for split questions
- Join confirmation before cross-dataset joins
- Per-result SQL preview
- Per-result charts only when useful, including bar, horizontal bar, line, area, pie, radial bar, treemap, radar, scatter, and histogram
- One final grounded summary for the whole user question
- Safe Mode and Dev Mode through environment variables

The first version intentionally does not support `.sql` dump uploads and does not persist chat history.

## Architecture

```text
askmydata/
  frontend/        Next.js, TypeScript, Tailwind, shadcn-style UI, Recharts
  backend/         FastAPI, Pydantic, SQLAlchemy, DuckDB, Pandas
```

The backend uses a safe two-path query flow:

1. Check that at least one source exists and that the question looks related to the available source names, columns, values, or a general data operation.
2. Route each independent sub-question to the most relevant source, or ask for source confirmation when the match is ambiguous.
3. Ask the LLM for one read-only SQL plan when a provider is configured. The prompt includes source metadata, dtypes, semantic types, sample values, and head rows.
4. Validate the LLM plan before execution: one statement only, `SELECT` only, known tables only, known columns only, no destructive SQL, and no joins unless the user confirms joins.
5. Fall back to the deterministic structured parser and allowlisted SQL builder whenever the LLM is unavailable, invalid, unsafe, or too ambiguous.
6. Execute retrieval-only operations: `select`, `filter`, `sort`, `limit`, `group by`, aggregate, top/bottom, comparison, trends, and confirmed joins.
7. Pick a chart per result when useful or explicitly requested, then generate one grounded final summary for the full question.

## Local Setup

Copy the environment template:

```bash
cp .env.example .env
```

Fill in at least:

```bash
APP_NAME=askmydata
APP_ENV=local
APP_MODE=safe
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=http://localhost:3000
MAX_TOTAL_FILES=5
MAX_FILE_SIZE_MB=10
DEFAULT_LLM_PROVIDER=cerebras
DEFAULT_LLM_MODEL=qwen-3-235b-a22b-instruct-2507
FALLBACK_LLM_PROVIDER=ollama
FALLBACK_LLM_MODEL=llama3.1
ENABLE_LLM_FALLBACK=false
CEREBRAS_MODEL=qwen-3-235b-a22b-instruct-2507
CEREBRAS_BASE_URL=https://api.cerebras.ai/v1
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_TIMEOUT_SECONDS=60
ENABLE_SQL_PREVIEW=true
ENABLE_CHARTS=true
ENABLE_LIGHT_CLEANING_PROMPT=true
ENABLE_MULTI_SOURCE_ROUTING=true
ENABLE_JOIN_CONFIRMATION=true
ENABLE_DEV_MODE_TOOLS=false
LOG_LEVEL=INFO
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Start the backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Docker Compose

```bash
docker compose up --build
```

The frontend runs at `http://localhost:3000` and the backend runs at `http://localhost:8000`.

## Deployment

Primary recommendation: Render-only full stack. This can give you a public link that anyone can open, as long as your Render services are public and the app does not add authentication.

Recommended Render setup:

1. Create a Render Web Service for `backend/`.
2. Use Docker as the backend runtime.
3. Add environment variables from `.env.example`.
4. Set `CORS_ORIGINS` and `FRONTEND_URL` to your frontend Render URL after it exists.
5. Create a Render Static Site or Web Service for `frontend/`.
6. Use:
   - Build command: `npm install && npm run build`
   - Start command for Web Service: `npm run start`
   - Publish directory for Static Site only if exporting static output later
7. Set `NEXT_PUBLIC_API_BASE_URL` to the public backend Render URL.

If the frontend shows a network error or “failed to fetch,” check these first:

- The backend service is running and `/health` returns `{"status":"ok"}`.
- `NEXT_PUBLIC_API_BASE_URL` in the frontend points to the public backend URL, not `localhost`, unless you are running locally.
- Backend `CORS_ORIGINS` includes the exact frontend URL.
- Backend `FRONTEND_URL` matches the frontend URL.

Optional path: Vercel frontend + Render backend.

1. Deploy `backend/` to Render as above.
2. Deploy `frontend/` to Vercel.
3. Set `NEXT_PUBLIC_API_BASE_URL` in Vercel to the Render backend URL.
4. Set backend `CORS_ORIGINS` to the Vercel URL.

## Safe Mode And Dev Mode

- `APP_MODE=safe`: default, minimal debug exposure.
- `APP_MODE=dev` or `ENABLE_DEV_MODE_TOOLS=true`: returns parser/planner debug metadata where supported.

Dev Mode still does not permit arbitrary destructive SQL.

## Testing Checklist

- Upload one CSV under 10 MB and confirm it appears in Workspace sources.
- Upload an XLSX file and choose the light cleaning option.
- Try uploading a sixth file and confirm the hard cap blocks it.
- Connect a SQLite database using a connection string.
- Connect PostgreSQL or MySQL with manual fields.
- Ask a plain fetch query and confirm no chart appears.
- Ask a trend/top-category query and confirm a chart appears inside that result block.
- Ask a multi-source question and confirm separate result sections appear.
- Ask a join-like question and confirm the inline join permission prompt appears first.
- Open “See generated SQL code?” and confirm it shows SQL only.
- Confirm only one final summary card appears for the full user question.

## Sample Natural-Language Queries

- Show the first 25 rows.
- Count records by status.
- Show the top 10 customers by revenue.
- Plot monthly sales over time.
- Compare order counts by region.
- What changed in rainfall over time?
- For each dataset, show top categories by count.
- Combine customers and orders to compare customer segment revenue.

## Notes

This is a recruiter-friendly first version. The deterministic parser is intentionally conservative so the execution path remains safe without requiring LLM credentials during local setup. The provider abstraction for Cerebras and Ollama is included so structured parsing and richer summarization can be expanded without changing the app surface.
