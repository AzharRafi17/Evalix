import csv
import io
import json

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from evaluations.engine import RAGEvaluatorEngine
from evaluations.llm_clients import get_llm_client
from evaluations.models import EvaluationRun, TestCase, TestSuite
from evaluations.serializers import BatchRequestSerializer, EvaluationInputSerializer
from evaluations.tasks import evaluate_run


def health_check(request):
    return JsonResponse({'status': 'ok', 'service': 'evalix'})


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
        run = get_object_or_404(EvaluationRun, pk=run_id, suite_id=suite_id)
        total = run.suite.test_cases.count()
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
