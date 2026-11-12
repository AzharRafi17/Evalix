import csv
import io
import json

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from evaluations.engine import RAGEvaluatorEngine
from evaluations.llm_clients import get_llm_client
from evaluations.models import EvaluationResult, EvaluationRun, TestCase, TestSuite
from evaluations.ownership import get_owner
from evaluations.serializers import BatchRequestSerializer, EvaluationInputSerializer
from evaluations.tasks import evaluate_run


def health_check(request):
    return JsonResponse({'status': 'ok', 'service': 'evalix'})


def visible_suites(request):
    suites = TestSuite.objects.all()
    if settings.AUTH_REQUIRED:
        suites = suites.filter(owner=request.user)
    return suites


class PublicTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    authentication_classes = []


class PublicTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []


class SingleEvaluationView(APIView):
    def post(self, request):
        serializer = EvaluationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            engine = RAGEvaluatorEngine(llm_client=get_llm_client())
            result = engine.evaluate_case(**serializer.validated_data)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result, status=status.HTTP_200_OK)


class BatchEvaluationView(APIView):
    CSV_REQUIRED_COLUMNS = {'query', 'retrieved_contexts', 'llm_response'}

    def post(self, request):
        content_length = request.META.get('CONTENT_LENGTH')
        if content_length and int(content_length) > settings.MAX_BATCH_BYTES:
            return Response({'detail': 'Batch payload exceeds the configured size limit.'}, status=413)

        uploaded_file = request.FILES.get('file')
        if uploaded_file:
            parsed = self._read_csv(uploaded_file)
            if isinstance(parsed, Response):
                return parsed
            data = {'cases': parsed}
            name = request.data.get('name', '')
            description = request.data.get('description', '')
            if name:
                data['name'] = name
            if description:
                data['description'] = description
        elif isinstance(request.data, list):
            data = {'cases': request.data}
        else:
            data = request.data

        serializer = BatchRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        cases = serializer.validated_data['cases']
        if len(cases) > settings.MAX_BATCH_CASES:
            return Response({'detail': f'Batch exceeds the {settings.MAX_BATCH_CASES}-case limit.'}, status=400)

        provider = settings.EVALUATOR_PROVIDER
        with transaction.atomic():
            suite = TestSuite.objects.create(
                name=serializer.validated_data.get('name') or f'Evaluation {timezone.now():%Y-%m-%d %H:%M:%S}',
                description=serializer.validated_data.get('description', ''),
                owner=get_owner(request.user),
            )
            TestCase.objects.bulk_create([
                TestCase(suite=suite, **case)
                for case in cases
            ])
            run = EvaluationRun.objects.create(
                suite=suite,
                judge_provider=provider,
                judge_model=settings.EVALUATOR_MODEL,
                prompt_version=settings.EVALUATOR_PROMPT_VERSION,
            )

        task = evaluate_run.delay(run.pk)
        return Response({
            'task_id': task.id,
            'suite_id': suite.pk,
            'run_id': run.pk,
        }, status=status.HTTP_202_ACCEPTED)

    def _read_csv(self, uploaded_file):
        if uploaded_file.size > settings.MAX_BATCH_BYTES:
            return Response({'detail': 'CSV file exceeds the configured size limit.'}, status=400)
        try:
            text = uploaded_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({'detail': 'CSV file must use UTF-8 encoding.'}, status=400)
        reader = csv.DictReader(io.StringIO(text))
        columns = set(reader.fieldnames or [])
        missing = self.CSV_REQUIRED_COLUMNS - columns
        if missing:
            return Response({'detail': f'CSV is missing required columns: {", ".join(sorted(missing))}.'}, status=400)
        rows = []
        try:
            for row in reader:
                contexts = json.loads(row.get('retrieved_contexts') or '[]')
                rows.append({
                    'query': row.get('query', ''),
                    'retrieved_contexts': contexts,
                    'llm_response': row.get('llm_response', ''),
                    'ground_truth': row.get('ground_truth') or None,
                })
                if len(rows) > settings.MAX_BATCH_CASES:
                    return Response({'detail': f'Batch exceeds the {settings.MAX_BATCH_CASES}-case limit.'}, status=400)
        except (ValueError, TypeError):
            return Response({'detail': 'Each retrieved_contexts CSV cell must contain a JSON array.'}, status=400)
        if not rows:
            return Response({'detail': 'CSV must contain at least one test case.'}, status=400)
        return rows


class RunStatusView(APIView):
    def get(self, request, suite_id, run_id):
        suite = get_object_or_404(visible_suites(request), pk=suite_id)
        run = get_object_or_404(EvaluationRun, pk=run_id, suite=suite)
        total = suite.test_cases.count()
        processed = run.results.count()
        failed = run.results.filter(status='failed').count()
        return Response({
            'suite_id': suite_id,
            'run_id': run_id,
            'status': run.status,
            'processed': processed,
            'total': total,
            'failed': failed,
        })


class SuiteListView(APIView):
    def get(self, request):
        suites = visible_suites(request).order_by('-created_at')
        payload = []
        for suite in suites:
            run = suite.runs.order_by('-started_at', '-id').first()
            results = run.results.filter(status='ok') if run else EvaluationResult.objects.none()
            total = results.count()
            faithfulness_values = [
                value for value in results.values_list('faithfulness_score', flat=True)
                if value is not None
            ]
            hallucination_count = results.filter(has_hallucination=True).count()
            payload.append({
                'id': suite.pk,
                'name': suite.name,
                'description': suite.description,
                'created_at': suite.created_at,
                'case_count': suite.test_cases.count(),
                'latest_run': ({
                    'id': run.pk,
                    'status': run.status,
                    'faithfulness_score': (
                        sum(faithfulness_values) / len(faithfulness_values)
                        if faithfulness_values else None
                    ),
                    'hallucination_rate': hallucination_count / total if total else None,
                    'total_tokens_in': run.total_tokens_in,
                    'total_tokens_out': run.total_tokens_out,
                    'total_cost': str(run.total_cost),
                } if run else None),
            })
        return Response(payload)


class SuiteDetailView(APIView):
    def get(self, request, suite_id):
        suite = get_object_or_404(visible_suites(request), pk=suite_id)
        runs = []
        for run in suite.runs.order_by('-started_at', '-id'):
            results = []
            for result in run.results.select_related('test_case').order_by('id'):
                results.append({
                    'id': result.pk,
                    'test_case_id': result.test_case_id,
                    'query': result.test_case.query,
                    'llm_response': result.test_case.llm_response,
                    'faithfulness_score': result.faithfulness_score,
                    'answer_relevance_score': result.answer_relevance_score,
                    'context_precision_score': result.context_precision_score,
                    'context_recall_score': result.context_recall_score,
                    'has_hallucination': result.has_hallucination,
                    'details': result.details,
                    'reasoning': result.reasoning,
                    'tokens_in': result.tokens_in,
                    'tokens_out': result.tokens_out,
                    'latency_ms': result.latency_ms,
                    'status': result.status,
                    'error_message': result.error_message,
                })
            runs.append({
                'id': run.pk,
                'status': run.status,
                'judge_provider': run.judge_provider,
                'judge_model': run.judge_model,
                'prompt_version': run.prompt_version,
                'results': results,
            })
        return Response({
            'id': suite.pk,
            'name': suite.name,
            'description': suite.description,
            'created_at': suite.created_at,
            'case_count': suite.test_cases.count(),
            'runs': runs,
        })


class SuiteCompareView(APIView):
    METRICS = (
        'faithfulness_score',
        'answer_relevance_score',
        'context_precision_score',
        'context_recall_score',
    )

    def get(self, request, suite_id):
        suite = get_object_or_404(visible_suites(request), pk=suite_id)
        try:
            run_a_id = int(request.query_params['run_a'])
            run_b_id = int(request.query_params['run_b'])
        except (KeyError, ValueError):
            return Response({'detail': 'run_a and run_b must be integer run IDs.'}, status=400)
        run_a = get_object_or_404(EvaluationRun, pk=run_a_id, suite=suite)
        run_b = get_object_or_404(EvaluationRun, pk=run_b_id, suite=suite)
        output = {}
        for metric in self.METRICS:
            value_a = self._average(run_a, metric)
            value_b = self._average(run_b, metric)
            output[metric] = {
                'run_a': value_a,
                'run_b': value_b,
                'difference': value_a - value_b if value_a is not None and value_b is not None else None,
            }
        return Response({'suite_id': suite.pk, 'metrics': output})

    @staticmethod
    def _average(run, field):
        values = [
            value for value in run.results.filter(status='ok').values_list(field, flat=True)
            if value is not None
        ]
        return sum(values) / len(values) if values else None


class SuiteExportView(APIView):
    HEADERS = (
        'run_id', 'test_case_id', 'query', 'llm_response', 'faithfulness_score',
        'answer_relevance_score', 'context_precision_score', 'context_recall_score',
        'has_hallucination', 'status', 'error_message',
    )

    def get(self, request, suite_id):
        suite = get_object_or_404(visible_suites(request), pk=suite_id)
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(self.HEADERS)
        results = EvaluationResult.objects.filter(run__suite=suite).select_related(
            'run', 'test_case',
        ).order_by('run_id', 'id')
        for result in results:
            writer.writerow([
                result.run_id,
                result.test_case_id,
                result.test_case.query,
                result.test_case.llm_response,
                result.faithfulness_score,
                result.answer_relevance_score,
                result.context_precision_score,
                result.context_recall_score,
                result.has_hallucination,
                result.status,
                result.error_message or '',
            ])
        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="evalix-suite-{suite.pk}.csv"'
        return response
