from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from benchmarks.models import BenchmarkRun
from benchmarks.service import _classification_metrics, _correlation, run_benchmark
from evaluations.models import BenchmarkDataset, BenchmarkItem


def test_classification_metrics_include_kappa_and_confusion_matrix():
    metrics = _classification_metrics([True, False], [True, True])

    assert metrics['accuracy'] == 0.5
    assert metrics['precision'] == 0.5
    assert metrics['recall'] == 1.0
    assert metrics['f1'] == pytest.approx(2 / 3)
    assert metrics['cohens_kappa'] == 0.0
    assert metrics['confusion_matrix'] == {
        'true_positive': 1,
        'true_negative': 0,
        'false_positive': 1,
        'false_negative': 0,
    }


def test_spearman_uses_average_ranks_for_ties():
    assert _correlation([1, 2, 3], [1, 3, 2]) == pytest.approx(0.5)
    assert _correlation([1, 1, 1], [1, 2, 3]) is None


@pytest.mark.django_db
def test_run_benchmark_reports_target_and_worst_disagreements():
    dataset = BenchmarkDataset.objects.create(name='Tiny benchmark')
    items = [
        BenchmarkItem.objects.create(
            dataset=dataset,
            query=f'Question {index}',
            retrieved_contexts=['Context'],
            llm_response='Answer',
            hallucination_label=label,
            faithfulness_score=float(not label),
            answer_relevance_score=1.0,
            context_precision_score=1.0,
            context_recall_score=1.0,
        )
        for index, label in enumerate([False, True])
    ]

    class FakeEngine:
        def evaluate_case(self, **kwargs):
            return {
                'has_hallucination': kwargs['query'] == 'Question 0',
                'faithfulness_score': 0.0,
                'answer_relevance_score': 0.5,
                'context_precision_score': 1.0,
                'context_recall_score': 1.0,
            }

    result = run_benchmark({'dataset_id': dataset.pk, 'engine': FakeEngine()})

    assert result['item_count'] == 2
    assert result['evaluated_count'] == 2
    assert result['hallucination_detection']['accuracy'] == 0.0
    assert result['accuracy_target_met'] is False
    assert {row['item_id'] for row in result['worst_disagreements']} == {item.pk for item in items}


@pytest.mark.django_db
def test_benchmark_api_dispatches_and_returns_stored_report():
    dataset = BenchmarkDataset.objects.create(name='API benchmark')
    client = APIClient()
    with patch('benchmarks.views.execute_benchmark.delay') as enqueue:
        enqueue.return_value.id = 'benchmark-task'
        response = client.post(reverse('benchmark-start'), {'dataset_id': dataset.pk}, format='json')

    assert response.status_code == 202
    run = BenchmarkRun.objects.get(pk=response.json()['id'])
    assert run.dataset_id == dataset.pk
    enqueue.assert_called_once_with(run.pk)

    run.metrics = {'hallucination_detection': {'accuracy': 0.5}}
    run.save(update_fields=['metrics'])
    detail = client.get(reverse('benchmark-detail', args=[run.pk]))
    assert detail.status_code == 200
    assert detail.json()['metrics']['hallucination_detection']['accuracy'] == 0.5


@pytest.mark.django_db
def test_sample_benchmark_seeder_creates_thirty_idempotent_items():
    call_command('seed_sample_benchmark', verbosity=0)
    call_command('seed_sample_benchmark', verbosity=0)

    dataset = BenchmarkDataset.objects.get(name='Evalix synthetic sample benchmark')
    assert dataset.is_sample is True
    assert dataset.source == 'synthetic-sample'
    assert dataset.items.count() == 30
    assert dataset.items.filter(hallucination_label=True).count() == 15