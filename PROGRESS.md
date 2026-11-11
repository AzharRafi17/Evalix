# Evalix Progress

## Completed phases
- Phase 1: Project setup complete, including initial Django migrations and a migration-application test
- Phase 2: Evaluator engine complete with Pydantic verdicts, OpenAI-compatible and Gemini clients, versioned injection-resistant prompts, retries, Django cache support (locmem in tests, Redis in production), scoring tests, and a real-provider smoke script
- Phase 3: Synchronous single-evaluation API, JSON/CSV batch ingestion, idempotent Celery processing with partial-failure handling, and run-status polling
- Phase 4: Reusable benchmark service, classification and score metrics, async benchmark API, management command, and 30-item synthetic sample dataset seeder

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
- backend/evaluations/serializers.py
- backend/evaluations/tasks.py
- backend/evaluations/migrations/0002_alter_evaluationresult_faithfulness_score_and_more.py
- backend/evaluations/tests/test_api.py
- backend/evaluations/tests/test_tasks.py
- backend/benchmarks/models.py
- backend/benchmarks/service.py
- backend/benchmarks/tasks.py
- backend/benchmarks/serializers.py
- backend/benchmarks/views.py
- backend/benchmarks/urls.py
- backend/benchmarks/migrations/0001_initial.py
- backend/benchmarks/management/commands/seed_sample_benchmark.py
- backend/benchmarks/management/commands/run_evaluator_benchmark.py
- backend/evaluations/tests/test_benchmark.py
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
- Phase 5: Build the Next.js playground, dashboard, batch upload, suite results, comparison, and benchmarks views.
