from celery import shared_task
from django.utils import timezone

from benchmarks.models import BenchmarkRun
from benchmarks.service import run_benchmark


@shared_task
def execute_benchmark(run_id):
    run = BenchmarkRun.objects.select_related('dataset').get(pk=run_id)
    run.status = 'processing'
    run.save(update_fields=['status'])
    try:
        metrics = run_benchmark({
            'dataset_id': run.dataset_id,
            'provider': run.judge_provider,
            'model': run.judge_model,
            'prompt_version': run.prompt_version,
        })
    except Exception as exc:
        run.status = 'failed'
        run.error_message = str(exc)[:4000]
    else:
        run.status = 'completed'
        run.item_count = metrics['item_count']
        run.evaluated_count = metrics['evaluated_count']
        run.metrics = metrics
        run.disagreements = metrics['worst_disagreements']
    run.finished_at = timezone.now()
    run.save(update_fields=[
        'status', 'item_count', 'evaluated_count', 'metrics', 'disagreements',
        'error_message', 'finished_at',
    ])
    return {'run_id': run.pk, 'status': run.status}