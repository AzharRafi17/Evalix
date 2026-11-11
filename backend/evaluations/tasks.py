from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from evaluations.engine import RAGEvaluatorEngine
from evaluations.llm_clients import get_llm_client
from evaluations.models import EvaluationResult, EvaluationRun


@shared_task(bind=True, rate_limit=settings.EVALUATION_TASK_RATE_LIMIT)
def evaluate_run(self, run_id):
    run = EvaluationRun.objects.select_related('suite').get(pk=run_id)
    run.status = 'processing'
    run.save(update_fields=['status'])
    client = get_llm_client(run.judge_provider)
    engine = RAGEvaluatorEngine(
        llm_client=client,
        model=run.judge_model,
        provider=run.judge_provider,
        prompt_version=run.prompt_version,
    )

    cases = run.suite.test_cases.order_by('id')
    chunk_size = max(1, settings.EVALUATION_TASK_CHUNK_SIZE)
    for offset in range(0, cases.count(), chunk_size):
        for test_case in cases[offset:offset + chunk_size]:
            existing = EvaluationResult.objects.filter(run=run, test_case=test_case).first()
            if existing and existing.status == 'ok':
                continue
            try:
                result = engine.evaluate_case(
                    query=test_case.query,
                    retrieved_contexts=test_case.retrieved_contexts,
                    llm_response=test_case.llm_response,
                    ground_truth=test_case.ground_truth,
                )
                defaults = {
                    'faithfulness_score': result['faithfulness_score'],
                    'answer_relevance_score': result['answer_relevance_score'],
                    'context_precision_score': result['context_precision_score'],
                    'context_recall_score': result['context_recall_score'],
                    'has_hallucination': result['has_hallucination'],
                    'details': result['details'],
                    'reasoning': result['reasoning'],
                    'tokens_in': result['tokens_in'],
                    'tokens_out': result['tokens_out'],
                    'latency_ms': result['latency_ms'],
                    'status': 'ok',
                    'error_message': None,
                }
            except Exception as exc:
                defaults = {
                    'status': 'failed',
                    'error_message': str(exc)[:4000],
                }
            with transaction.atomic():
                EvaluationResult.objects.update_or_create(
                    run=run,
                    test_case=test_case,
                    defaults=defaults,
                )

    results = run.results.all()
    run.total_tokens_in = sum(results.values_list('tokens_in', flat=True))
    run.total_tokens_out = sum(results.values_list('tokens_out', flat=True))
    run.total_cost = Decimal(
        (run.total_tokens_in + run.total_tokens_out)
        * settings.EVALUATOR_COST_PER_1K_TOKENS / 1000
    )
    failed_count = results.filter(status='failed').count()
    run.status = 'failed' if failed_count and failed_count == results.count() else 'completed'
    run.finished_at = timezone.now()
    run.save(update_fields=[
        'total_tokens_in', 'total_tokens_out', 'total_cost', 'status', 'finished_at',
    ])
    return {
        'run_id': run.pk,
        'processed': results.count(),
        'failed': failed_count,
        'status': run.status,
    }
