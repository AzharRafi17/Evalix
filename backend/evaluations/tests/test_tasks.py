from unittest.mock import patch

import pytest

from evaluations.models import EvaluationResult, EvaluationRun, TestCase, TestSuite
from evaluations.tasks import evaluate_run


def make_case(suite, query):
    return TestCase.objects.create(
        suite=suite,
        query=query,
        retrieved_contexts=['Context'],
        llm_response='Answer',
    )


def evaluation_result():
    return {
        'faithfulness_score': 1.0,
        'answer_relevance_score': 0.8,
        'context_precision_score': 1.0,
        'context_recall_score': None,
        'has_hallucination': False,
        'details': {},
        'reasoning': '',
        'tokens_in': 10,
        'tokens_out': 5,
        'latency_ms': 100,
    }


@pytest.mark.django_db
def test_evaluate_run_records_partial_failure_and_continues():
    suite = TestSuite.objects.create(name='Partial run')
    failed_case = make_case(suite, 'first')
    successful_case = make_case(suite, 'second')
    run = EvaluationRun.objects.create(suite=suite)

    def evaluate_case(*, query, **kwargs):
        if query == 'first':
            raise RuntimeError('judge unavailable')
        return evaluation_result()

    with patch('evaluations.tasks.get_llm_client'), patch(
        'evaluations.tasks.RAGEvaluatorEngine.evaluate_case', side_effect=evaluate_case
    ) as evaluate:
        outcome = evaluate_run.run(run.pk)

    assert outcome == {'run_id': run.pk, 'processed': 2, 'failed': 1, 'status': 'completed'}
    assert EvaluationResult.objects.get(run=run, test_case=failed_case).status == 'failed'
    assert EvaluationResult.objects.get(run=run, test_case=successful_case).status == 'ok'
    assert evaluate.call_count == 2


@pytest.mark.django_db
def test_evaluate_run_rerun_skips_successful_results():
    suite = TestSuite.objects.create(name='Idempotent run')
    test_case = make_case(suite, 'question')
    run = EvaluationRun.objects.create(suite=suite)

    with patch('evaluations.tasks.get_llm_client'), patch(
        'evaluations.tasks.RAGEvaluatorEngine.evaluate_case', return_value=evaluation_result()
    ) as evaluate:
        evaluate_run.run(run.pk)
        evaluate_run.run(run.pk)

    assert evaluate.call_count == 1
    assert EvaluationResult.objects.filter(run=run, test_case=test_case).count() == 1
    assert run.results.get(test_case=test_case).status == 'ok'