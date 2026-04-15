# AskMyData

AskMyData is a full-stack app where a user can upload data sources, ask normal English questions, get safe SQL-backed records, see smart visualizations, and read one final summary.

Live links:

- Frontend: https://frontend-alpha-vert-6xsr9y8hfi.vercel.app
- Backend health: https://askmydata-backend-live.onrender.com/health

## What It Does

- Upload CSV/XLSX files or connect SQLite, MySQL, and PostgreSQL sources.
- Keep a workspace of up to 5 sources at once.
- Split multi-part questions into separate interactive result tabs.
- Route every subquery to the best matching source using source metadata, columns, sample values, and head rows.
- Generate and validate read-only SQL only. No destructive SQL is allowed.
- Show retrieved records first, then Visual and SQL tabs.
- Use chart intent plus retrieved rows to pick useful charts like bar, line, area, pie, treemap, radial, radar, scatter, and histogram.
- Summarize the full original question using all retrieved result blocks.

## Run Locally

Create env:

```bash
cp .env.example .env
```

Set at least:

```bash
CEREBRAS_API_KEY=your_key
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=http://localhost:3000
```

Start backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Start frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Project Flow

```text
User uploads/ connects data
        |
Workspace stores source metadata, columns, sample values, and head rows
        |
User asks one question, or a question with multiple subqueries
        |
Router matches each subquery to the right data source
        |
LLM plans read-only SQL with strict rules
        |
SQL is validated again before execution
        |
Records are retrieved from the selected source
        |
Visualization planner chooses a chart from the actual retrieved rows
        |
UI shows Records, Visual, and SQL tabs for each subquery
        |
Final summary answers the full original question
```

## Deploy

Recommended setup:

- Backend on Render using `render.yaml`.
- Frontend on Vercel from the `frontend/` folder.
- Set `NEXT_PUBLIC_API_BASE_URL` in Vercel to the public Render backend URL.
- Set `FRONTEND_URL` and `CORS_ORIGINS` in Render to the public Vercel frontend URL.
- Set `CEREBRAS_API_KEY` in Render as a secret environment variable.

## Checks

```bash
cd backend && python -m pytest -q
cd frontend && npm run lint && npm run build
```
