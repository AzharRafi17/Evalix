from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from benchmarks.models import BenchmarkRun
from benchmarks.serializers import BenchmarkRunSerializer, BenchmarkStartSerializer
from benchmarks.tasks import execute_benchmark


class BenchmarkStartView(APIView):
    def post(self, request):
        serializer = BenchmarkStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = BenchmarkRun.objects.create(
            dataset=serializer.validated_data['dataset'],
            judge_provider=settings.EVALUATOR_PROVIDER,
            judge_model=settings.EVALUATOR_MODEL,
            prompt_version=settings.EVALUATOR_PROMPT_VERSION,
        )
        task = execute_benchmark.delay(run.pk)
        return Response(
            {'id': run.pk, 'task_id': task.id, 'status': run.status},
            status=status.HTTP_202_ACCEPTED,
        )


class BenchmarkDetailView(APIView):
    def get(self, request, benchmark_id):
        run = get_object_or_404(BenchmarkRun, pk=benchmark_id)
        return Response(BenchmarkRunSerializer(run).data)