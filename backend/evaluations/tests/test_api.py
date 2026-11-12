import json
import csv
import io
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client as DjangoClient, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import AnonRateThrottle

from evaluations.models import EvaluationResult, EvaluationRun, TestCase, TestSuite


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


@pytest.mark.django_db
def test_suite_list_detail_and_comparison_return_aggregates():
    client = APIClient()
    suite = TestSuite.objects.create(name='Comparison suite')
    test_case = TestCase.objects.create(
        suite=suite,
        query='Question?',
        retrieved_contexts=['Context'],
        llm_response='Answer',
    )
    run_a = EvaluationRun.objects.create(suite=suite)
    run_b = EvaluationRun.objects.create(suite=suite)
    EvaluationResult.objects.create(
        run=run_a,
        test_case=test_case,
        faithfulness_score=0.8,
        answer_relevance_score=0.6,
        context_precision_score=1.0,
        context_recall_score=0.5,
        has_hallucination=False,
    )
    EvaluationResult.objects.create(
        run=run_b,
        test_case=test_case,
        faithfulness_score=0.4,
        answer_relevance_score=0.8,
        context_precision_score=0.5,
        context_recall_score=None,
        has_hallucination=True,
    )

    listing = client.get(reverse('evaluation-suites'))
    detail = client.get(reverse('evaluation-suite-detail', args=[suite.pk]))
    comparison = client.get(reverse('evaluation-suite-compare', args=[suite.pk]), {
        'run_a': run_a.pk,
        'run_b': run_b.pk,
    })

    assert listing.status_code == 200
    assert listing.json()[0]['case_count'] == 1
    assert listing.json()[0]['latest_run']['hallucination_rate'] == 1.0
    assert detail.json()['runs'][0]['results'][0]['query'] == 'Question?'
    assert comparison.json()['metrics']['faithfulness_score']['difference'] == pytest.approx(0.4)
    assert comparison.json()['metrics']['context_recall_score']['difference'] is None


@pytest.mark.django_db
def test_anonymous_batch_uses_demo_user_owner(settings):
    settings.AUTH_REQUIRED = False
    client = APIClient()
    with patch('evaluations.views.evaluate_run.delay') as enqueue:
        enqueue.return_value.id = 'demo-task'
        response = client.post(reverse('evaluation-batch'), {
            'cases': [{'query': 'Q', 'retrieved_contexts': [], 'llm_response': 'A'}],
        }, format='json')

    suite = TestSuite.objects.get(pk=response.json()['suite_id'])
    demo_user = get_user_model().objects.get(username=settings.DEMO_USERNAME)
    assert response.status_code == 202
    assert suite.owner == demo_user
    assert not demo_user.has_usable_password()


@pytest.mark.django_db
def test_jwt_endpoints_and_required_suite_ownership(settings):
    settings.AUTH_REQUIRED = True
    call_command('create_evalix_user', 'alice', password='test-password')
    call_command('create_evalix_user', 'bob', password='test-password')
    user_model = get_user_model()
    alice = user_model.objects.get(username='alice')
    bob = user_model.objects.get(username='bob')
    alice_suite = TestSuite.objects.create(name='Alice', owner=alice)
    bob_suite = TestSuite.objects.create(name='Bob', owner=bob)
    bob_run = EvaluationRun.objects.create(suite=bob_suite)
    client = APIClient()

    token_response = client.post(reverse('token-obtain-pair'), {
        'username': 'alice', 'password': 'test-password',
    }, format='json')
    assert token_response.status_code == 200
    refresh_response = client.post(reverse('token-refresh'), {
        'refresh': token_response.json()['refresh'],
    }, format='json')
    assert refresh_response.status_code == 200

    settings.AUTH_REQUIRED = False
    with override_settings(AUTH_REQUIRED=True):
        assert client.get(reverse('evaluation-suites')).status_code == 401
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.json()['access']}")
        listing = client.get(reverse('evaluation-suites'))
        assert [row['id'] for row in listing.json()] == [alice_suite.pk]
        assert client.get(reverse('evaluation-suite-detail', args=[bob_suite.pk])).status_code == 404
        assert client.get(reverse('evaluation-suite-export', args=[bob_suite.pk])).status_code == 404
        assert client.get(
            reverse('evaluation-run-status', args=[bob_suite.pk, bob_run.pk])
        ).status_code == 404
        with patch('evaluations.views.evaluate_run.delay') as enqueue:
            enqueue.return_value.id = 'alice-task'
            created = client.post(reverse('evaluation-batch'), {
                'cases': [{'query': 'Q', 'retrieved_contexts': [], 'llm_response': 'A'}],
            }, format='json')
            assert created.status_code == 202
            assert TestSuite.objects.get(pk=created.json()['suite_id']).owner == alice
            bob_token = client.post(reverse('token-obtain-pair'), {
                'username': 'bob', 'password': 'test-password',
            }, format='json')
            assert bob_token.status_code == 200
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {bob_token.json()['access']}")
            assert client.get(reverse('evaluation-suite-detail', args=[alice_suite.pk])).status_code == 404


@pytest.mark.django_db
def test_suite_export_returns_csv_rows():
    suite = TestSuite.objects.create(name='Export suite')
    case = TestCase.objects.create(
        suite=suite,
        query='Question, with comma?',
        retrieved_contexts=['Context'],
        llm_response='Answer',
    )
    run = EvaluationRun.objects.create(suite=suite)
    EvaluationResult.objects.create(
        run=run,
        test_case=case,
        faithfulness_score=0.75,
        answer_relevance_score=0.5,
        context_precision_score=1.0,
        has_hallucination=True,
    )

    response = APIClient().get(reverse('evaluation-suite-export', args=[suite.pk]))
    rows = list(csv.reader(io.StringIO(response.content.decode('utf-8'))))

    assert response.status_code == 200
    assert response['Content-Type'].startswith('text/csv')
    assert response['Content-Disposition'].endswith(f'evalix-suite-{suite.pk}.csv"')
    assert rows[1][2:5] == ['Question, with comma?', 'Answer', '0.75']


@pytest.mark.django_db
def test_evaluation_endpoint_is_throttled(settings, monkeypatch):
    settings.AUTH_REQUIRED = False
    monkeypatch.setattr(AnonRateThrottle, 'THROTTLE_RATES', {'anon': '1/minute'})
    cache.clear()
    client = APIClient()
    with patch('evaluations.views.get_llm_client'), patch(
        'evaluations.views.RAGEvaluatorEngine.evaluate_case', return_value={'ok': True}
    ):
        payload = {'query': 'Q', 'retrieved_contexts': [], 'llm_response': 'A'}
        first = client.post(reverse('evaluation-single'), payload, format='json')
        second = client.post(reverse('evaluation-single'), payload, format='json')

    assert first.status_code == 200
    assert second.status_code == 429


def test_cors_allows_only_configured_frontend_origin(settings):
    assert settings.CORS_ALLOW_ALL_ORIGINS is False
    assert settings.CORS_ALLOWED_ORIGINS == [settings.FRONTEND_ORIGIN]
    settings.CORS_ALLOW_ALL_ORIGINS = False
    settings.CORS_ALLOWED_ORIGINS = ['https://frontend.example.test']
    client = DjangoClient()

    allowed = client.get(reverse('health-check'), HTTP_ORIGIN='https://frontend.example.test')
    denied = client.get(reverse('health-check'), HTTP_ORIGIN='https://other.example.test')

    assert allowed.get('Access-Control-Allow-Origin') == 'https://frontend.example.test'
    assert denied.get('Access-Control-Allow-Origin') is None
