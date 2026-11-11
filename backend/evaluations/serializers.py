from rest_framework import serializers


class EvaluationInputSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=20000)
    retrieved_contexts = serializers.ListField(
        child=serializers.CharField(max_length=20000),
        max_length=100,
    )
    llm_response = serializers.CharField(max_length=50000)
    ground_truth = serializers.CharField(max_length=50000, allow_blank=True, allow_null=True, required=False)


class BatchRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    cases = EvaluationInputSerializer(many=True, allow_empty=False)
