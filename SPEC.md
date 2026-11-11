# Project: Evalix — RAG Quality Judge Platform

You are a senior full-stack AI engineer. Build "Evalix", a platform that evaluates RAG applications using an LLM-as-a-Judge approach, plus a benchmarking module that measures how trustworthy the judge itself is. Work in phases. After each phase, run the tests, fix failures, and update PROGRESS.md, then continue to the next phase. Prefer simple, readable code over clever code. Explain non-obvious decisions in short comments.

## Stack
- Backend: Python 3.11+, Django 4.2+, Django REST Framework, drf-spectacular (OpenAPI docs)
- Async: Celery + Redis
- DB: PostgreSQL (JSONB for detailed metric output)
- Auth: JWT (djangorestframework-simplejwt). API key auth is optional, only in the last phase.
- Frontend: Next.js 14+ (App Router), TypeScript, Tailwind CSS, TanStack Query
- Infra: Docker Compose (web, worker, postgres, redis), .env for all secrets, GitHub Actions CI (lint + tests)

## Input and core concepts
Input per test case: query, retrieved_contexts (list of strings), llm_response, optional ground_truth.

## Evaluation engine (most important part)
Create a `RAGEvaluatorEngine` service class. Do NOT ask the LLM to output final float scores directly. Ask the LLM for structured verdicts, validate them with Pydantic, and compute scores in code.

Metrics:
1. Faithfulness: LLM extracts atomic claims from the response, then labels each claim supported / unsupported / contradicted by the contexts. Score = supported claims / total claims. has_hallucination = true if any claim is unsupported or contradicted.
2. Answer Relevance: LLM rates how directly the response answers the query on a 1-5 rubric with written anchors for each level. Normalize to 0-1.
3. Context Precision: LLM labels each retrieved chunk relevant / not relevant to the query. Score = precision@k, rank-aware (relevant chunks ranked earlier score higher).
4. Context Recall (only when ground_truth exists): what fraction of ground-truth statements are covered by the retrieved contexts.

Engineering rules:
- One separate prompt per metric. Prompts live in versioned files (e.g. prompts/v1/faithfulness.txt) and every result stores the prompt_version.
- Judge LLM access goes through a provider abstraction (`BaseLLMClient`) with implementations for at least two providers (OpenAI-compatible and Gemini or Groq). Model name, temperature (default 0), and provider come from settings.
- Enforce JSON output, validate with Pydantic, retry up to 3 times on invalid output or API errors with exponential backoff, and record token usage, latency, and estimated cost per call.
- Cache identical (input + judge model + prompt_version) evaluations to avoid duplicate cost.
- Fully mockable: the engine receives its LLM client via dependency injection.

## Database models (`evaluations` app)
- TestSuite: id, owner, name, description, created_at
- TestCase: suite FK, query, retrieved_contexts (JSONB), llm_response, ground_truth (nullable)
- EvaluationRun: suite FK, judge_provider, judge_model, prompt_version, status (pending/processing/completed/failed), started_at, finished_at, totals for tokens and cost. A suite can have many runs so I can compare judges and prompts.
- EvaluationResult: run FK, test_case FK, faithfulness_score, answer_relevance_score, context_precision_score, context_recall_score (nullable), has_hallucination, details (JSONB: claims, per-chunk verdicts), reasoning, tokens_in, tokens_out, latency_ms, status (ok/failed), error_message
- BenchmarkDataset and BenchmarkItem: golden cases with human labels (hallucination yes/no, plus human scores for the metrics), source field (self-labeled or public dataset name)

## Async pipeline
- POST /api/v1/evaluations/batch/ accepts a JSON list or CSV file (validate size limit and columns, return clear 400 errors). It creates the suite, test cases, and a run, dispatches the Celery task, and returns 202 with task_id, suite_id, run_id.
- The Celery task processes items in chunks with a configurable concurrency and rate limit. One failed item must not fail the batch: mark that result as failed and continue. Retries must be idempotent.
- GET /api/v1/evaluations/suites/{suite_id}/runs/{run_id}/status/ returns processed/total, failed count, and status for polling.

## Benchmarking the judge
One service function `run_benchmark(judge_config)` used by both `python manage.py run_evaluator_benchmark` and `POST /api/v1/benchmarks/run/` (async). Compute and store:
- Hallucination detection: accuracy, precision, recall, F1, Cohen's kappa
- Score metrics: Spearman correlation and mean absolute error vs human scores
- Optional baseline: run RAGAS on the same dataset and compare against my judge in one table
- Target: at least 85% accuracy on hallucination detection. Report honestly if not met and list the worst disagreements for analysis.
Include a script to seed a small sample benchmark dataset (at least 30 items, clearly marked as sample data).

## API summary
- POST /api/v1/auth/token/ and /refresh/
- POST /api/v1/evaluations/single/ (sync playground)
- POST /api/v1/evaluations/batch/
- GET /api/v1/evaluations/suites/ and /suites/{id}/ (results + aggregate metrics)
- GET /api/v1/evaluations/suites/{id}/runs/{run_id}/status/
- GET /api/v1/evaluations/suites/{id}/compare/?run_a=&run_b= (metric differences between two runs)
- GET /api/v1/evaluations/suites/{id}/export/ (CSV)
- POST /api/v1/benchmarks/run/ and GET /api/v1/benchmarks/{id}/
- GET /api/v1/health/

## Frontend
Clean, minimal design with a consistent layout, light cards, clear spacing, no clutter.
- /dashboard: metric cards (total evaluations, avg faithfulness, hallucination rate, total tokens and cost) and recent suites table with status badges
- /playground: form (query, context chunks, response, optional ground truth), "Evaluate" button, scorecard with gauges, claim-by-claim faithfulness breakdown, and reasoning
- /evaluations/new: dropzone for CSV/JSON with client-side validation and a downloadable sample file
- /evaluations/[suite_id]: polling progress bar, results table with hallucination badges, expandable row for details, run selector and compare view
- /benchmarks: run benchmark, show accuracy, kappa, correlation, confusion matrix, and (if available) RAGAS comparison
Use TanStack Query, with structure components/ui, components/evaluations, hooks/, lib/api.ts. Handle loading, empty, and error states everywhere.

## Testing and quality
- Backend: pytest + pytest-django. Mock the LLM client; never call real APIs in tests. Cover scoring math, Pydantic validation and retries, the batch endpoint, partial failures, and benchmark metrics.
- Frontend: basic tests for the main hooks and the scorecard component.
- Add logging (structured), input limits, rate limiting on evaluation endpoints, and no secrets in the repo.

## Phases (stop after each one)
1. Project setup: Django, Docker Compose, settings, models, migrations, health endpoint, CI
2. Evaluator engine + provider abstraction + prompts + unit tests (no API yet)
3. Single evaluation endpoint + batch pipeline with Celery + status endpoint + tests
4. Benchmark module + sample dataset + RAGAS baseline comparison
5. Next.js frontend: playground and dashboard first, then batch upload, suite details, compare, benchmarks
6. Polish: auth hardening, optional API keys, export, README with architecture diagram, setup instructions, results table, and demo GIF checklist

## Definition of done
`docker compose up` starts everything, the tests pass, the README explains the architecture and the judge's measured accuracy, and a new user can run a sample batch evaluation in under 10 minutes.