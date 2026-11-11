from rest_framework import serializers

from benchmarks.models import BenchmarkRun
from evaluations.models import BenchmarkDataset


class BenchmarkStartSerializer(serializers.Serializer):
    dataset_id = serializers.PrimaryKeyRelatedField(
        queryset=BenchmarkDataset.objects.all(),
        source='dataset',
    )


class BenchmarkRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = BenchmarkRun
        fields = (
            'id', 'dataset_id', 'judge_provider', 'judge_model', 'prompt_version',
            'status', 'item_count', 'evaluated_count', 'metrics', 'disagreements',
            'error_message', 'started_at', 'finished_at',
        )