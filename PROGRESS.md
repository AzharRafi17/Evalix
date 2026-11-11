# Evalix Progress

## Completed phases
- Phase 1: Project setup complete, including initial Django migrations and a migration-application test
- Phase 2: Evaluator engine complete with Pydantic verdicts, OpenAI-compatible and Gemini clients, versioned injection-resistant prompts, retries, Django cache support (locmem in tests, Redis in production), scoring tests, and a real-provider smoke script

## Files created
- .env.example
- .gitignore
- README.md
- docker-compose.yml
- .github/workflows/ci.yml
- backend/Dockerfile
- backend/requirements.txt
- backend/manage.py
- backend/pytest.ini
- backend/core/__init__.py
- backend/core/celery.py
- backend/core/settings.py
- backend/core/urls.py
- backend/core/asgi.py
- backend/core/wsgi.py
- backend/evaluations/__init__.py
- backend/evaluations/apps.py
- backend/evaluations/models.py
- backend/evaluations/views.py
- backend/evaluations/urls.py
- backend/evaluations/tests/test_health.py
- backend/evaluations/engine.py
- backend/evaluations/llm_clients.py
- backend/evaluations/prompts/v1/faithfulness.txt
- backend/evaluations/prompts/v1/answer_relevance.txt
- backend/evaluations/prompts/v1/context_precision.txt
- backend/evaluations/prompts/v1/context_recall.txt
- backend/evaluations/tests/test_engine.py
- backend/scripts/smoke_eval.py
- backend/benchmarks/__init__.py
- backend/benchmarks/apps.py

## How to run and test
- Project root: `C:\dev\RAG-Evaluator`
- Backend environment: `py -3.11 -m venv .venv` then `.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
- Run tests: `.\.venv\Scripts\python.exe -m pytest backend -q`
- Start Django: `.\.venv\Scripts\python.exe backend\manage.py runserver`
- Start docker stack: `docker compose up`
- Run a real-provider smoke evaluation: `.\.venv\Scripts\python.exe backend\scripts\smoke_eval.py` (requires provider credentials in `.env`)

## Next phase
- Phase 3: Add sync evaluation and batch API endpoints, Celery processing, polling status, and tests.
