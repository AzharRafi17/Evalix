from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from benchmarks.models import BenchmarkRun
from benchmarks.serializers import BenchmarkRunSerializer, BenchmarkStartSerializer
from benchmarks.tasks import execute_benchmark
from evaluations.models import BenchmarkDataset
from evaluations.ownership import get_owner


class BenchmarkStartView(APIView):
    def post(self, request):
        serializer = BenchmarkStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = BenchmarkRun.objects.create(
            dataset=serializer.validated_data['dataset'],
            owner=get_owner(request.user),
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
        runs = BenchmarkRun.objects.all()
        if settings.AUTH_REQUIRED:
            runs = runs.filter(owner=request.user)
        run = get_object_or_404(runs, pk=benchmark_id)
        return Response(BenchmarkRunSerializer(run).data)


class BenchmarkDatasetListView(APIView):
    def get(self, request):
        datasets = BenchmarkDataset.objects.order_by('name')
        return Response([{
            'id': dataset.pk,
            'name': dataset.name,
            'item_count': dataset.items.count(),
            'is_sample': dataset.is_sample,
        } for dataset in datasets])