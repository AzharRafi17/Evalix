# Evalix Progress

## Completed phases
- Phase 1: Project setup complete, including initial Django migrations and a migration-application test

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
- backend/benchmarks/__init__.py
- backend/benchmarks/apps.py

## How to run and test
- Project root: `C:\dev\RAG-Evaluator`
- Backend environment: `py -3.11 -m venv .venv` then `.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
- Run tests: `.\.venv\Scripts\python.exe -m pytest backend -q`
- Start Django: `.\.venv\Scripts\python.exe backend\manage.py runserver`
- Start docker stack: `docker compose up`

## Next phase
- Phase 2: Implement the evaluator engine with provider abstraction, prompt files, and unit tests before enabling API endpoints.
