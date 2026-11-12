# Evalix

Evalix is a lightweight RAG evaluation platform that combines LLM-as-a-judge scoring with a benchmark harness for trustworthiness analysis.

## Architecture

```text
Client -> Next.js frontend -> Django REST API -> Celery workers -> PostgreSQL + Redis
                          \-> RAGEvaluatorEngine -> LLM providers
```

## Local setup without Docker

From PowerShell in `C:\dev\RAG-Evaluator`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
\.venv\Scripts\python.exe backend\manage.py migrate
\.venv\Scripts\python.exe backend\manage.py runserver
```

Local settings use SQLite at `backend\db.sqlite3` and eager Celery tasks, so a local run does not require Docker, PostgreSQL, Redis, or a copied `.env`. Docker Compose sets `IN_DOCKER=true` and uses its PostgreSQL and Redis services.

Install frontend dependencies with `npm install` from `frontend` when working on the frontend. Start the Docker services from the project root with `docker compose up`.

## Running tests

- Backend (from `C:\dev\RAG-Evaluator`): `.\.venv\Scripts\python.exe -m pytest backend -q`
- Frontend (from `C:\dev\RAG-Evaluator\frontend`): `npm test`

## Real-provider smoke evaluation

Configure `EVALUATOR_PROVIDER` and the matching API key in `.env`, then run one live evaluation from the project root:

```powershell
.\.venv\Scripts\python.exe backend\scripts\smoke_eval.py
```

This command calls the configured LLM provider and prints the structured evaluation result, including token usage and estimated cost.

## Notes

- The project uses a mockable judge abstraction so tests never hit real LLM APIs.
- Benchmarking compares human labels to the judge and reports honest accuracy and disagreement analysis.
