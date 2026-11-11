import json
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from evaluations.models import EvaluationRun, TestCase, TestSuite


@pytest.mark.django_db
def test_single_evaluation_validates_and_returns_engine_result():
    client = APIClient()
    result = {
        'faithfulness_score': 0.5,
        'answer_relevance_score': 0.75,
        'context_precision_score': 0.833,
        'context_recall_score': None,
        'has_hallucination': True,
    }
    with patch('evaluations.views.get_llm_client'), patch(
        'evaluations.views.RAGEvaluatorEngine.evaluate_case', return_value=result
    ):
        response = client.post(reverse('evaluation-single'), {
            'query': 'Question?',
            'retrieved_contexts': ['Context'],
            'llm_response': 'Answer',
        }, format='json')

    assert response.status_code == 200
    assert response.json()['faithfulness_score'] == 0.5


@pytest.mark.django_db
def test_batch_json_creates_suite_cases_and_run():
    client = APIClient()
    with patch('evaluations.views.evaluate_run.delay') as enqueue:
        enqueue.return_value.id = 'task-123'
        response = client.post(reverse('evaluation-batch'), {
            'name': 'Smoke suite',
            'cases': [{
                'query': 'Question?',
                'retrieved_contexts': ['Context'],
                'llm_response': 'Answer',
            }],
        }, format='json')

    assert response.status_code == 202
    payload = response.json()
    assert payload['task_id'] == 'task-123'
    assert TestSuite.objects.get(pk=payload['suite_id']).test_cases.count() == 1
    assert EvaluationRun.objects.get(pk=payload['run_id']).suite_id == payload['suite_id']
    enqueue.assert_called_once_with(payload['run_id'])


@pytest.mark.django_db
def test_batch_accepts_csv_and_rejects_missing_columns():
    client = APIClient()
    upload = SimpleUploadedFile(
        'cases.csv',
        b'query,retrieved_contexts,llm_response\nQuestion?,["Context"],Answer\n',
        content_type='text/csv',
    )
    with patch('evaluations.views.evaluate_run.delay') as enqueue:
        enqueue.return_value.id = 'task-csv'
        response = client.post(reverse('evaluation-batch'), {'file': upload}, format='multipart')
    assert response.status_code == 202
    case = TestCase.objects.get(suite_id=response.json()['suite_id'])
    assert case.retrieved_contexts == ['Context']

    invalid_upload = SimpleUploadedFile('bad.csv', b'question,response\na,b\n', content_type='text/csv')
    invalid = client.post(reverse('evaluation-batch'), {'file': invalid_upload}, format='multipart')
    assert invalid.status_code == 400
    assert 'missing required columns' in invalid.json()['detail']


@pytest.mark.django_db
def test_batch_rejects_invalid_context_json_in_csv():
    client = APIClient()
    upload = SimpleUploadedFile(
        'cases.csv',
        b'query,retrieved_contexts,llm_response\nQuestion?,not-json,Answer\n',
        content_type='text/csv',
    )
    response = client.post(reverse('evaluation-batch'), {'file': upload}, format='multipart')

    assert response.status_code == 400
    assert 'JSON array' in response.json()['detail']


@pytest.mark.django_db
def test_run_status_reports_processed_and_failed_counts():
    client = APIClient()
    suite = TestSuite.objects.create(name='Status suite')
    test_case = TestCase.objects.create(
        suite=suite,
        query='Question?',
        retrieved_contexts=[],
        llm_response='Answer',
    )
    run = EvaluationRun.objects.create(suite=suite)
    from evaluations.models import EvaluationResult
    EvaluationResult.objects.create(run=run, test_case=test_case, status='failed', error_message='timeout')

    response = client.get(reverse('evaluation-run-status', args=[suite.pk, run.pk]))

    assert response.status_code == 200
    assert response.json() == {
        'suite_id': suite.pk,
        'run_id': run.pk,
        'status': 'pending',
        'processed': 1,
        'total': 1,
        'failed': 1,
    }
