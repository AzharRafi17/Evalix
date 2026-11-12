from django.conf import settings
from django.db import models

from evaluations.ownership import get_default_owner_id


class TestSuite(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='test_suites',
        on_delete=models.CASCADE,
        default=get_default_owner_id,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TestCase(models.Model):
    suite = models.ForeignKey(TestSuite, related_name='test_cases', on_delete=models.CASCADE)
    query = models.TextField()
    retrieved_contexts = models.JSONField(default=list)
    llm_response = models.TextField()
    ground_truth = models.TextField(blank=True, null=True)


class EvaluationRun(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    suite = models.ForeignKey(TestSuite, related_name='runs', on_delete=models.CASCADE)
    judge_provider = models.CharField(max_length=50, default='mock')
    judge_model = models.CharField(max_length=100, default='mock-model')
    prompt_version = models.CharField(max_length=50, default='v1')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    total_tokens_in = models.BigIntegerField(default=0)
    total_tokens_out = models.BigIntegerField(default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)


class EvaluationResult(models.Model):
    STATUS_CHOICES = [
        ('ok', 'OK'),
        ('failed', 'Failed'),
    ]

    run = models.ForeignKey(EvaluationRun, related_name='results', on_delete=models.CASCADE)
    test_case = models.ForeignKey(TestCase, related_name='evaluation_results', on_delete=models.CASCADE)
    faithfulness_score = models.FloatField(blank=True, null=True)
    answer_relevance_score = models.FloatField(default=0.0)
    context_precision_score = models.FloatField(default=0.0)
    context_recall_score = models.FloatField(blank=True, null=True)
    has_hallucination = models.BooleanField(default=False)
    details = models.JSONField(default=dict)
    reasoning = models.TextField(blank=True)
    tokens_in = models.IntegerField(default=0)
    tokens_out = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ok')
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('run', 'test_case'), name='unique_run_test_case_result'),
        ]


class BenchmarkDataset(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=128, default='self-labeled')
    is_sample = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class BenchmarkItem(models.Model):
    dataset = models.ForeignKey(BenchmarkDataset, related_name='items', on_delete=models.CASCADE)
    query = models.TextField()
    retrieved_contexts = models.JSONField(default=list)
    llm_response = models.TextField()
    ground_truth = models.TextField(blank=True, null=True)
    hallucination_label = models.BooleanField(default=False)
    faithfulness_score = models.FloatField(default=0.0)
    answer_relevance_score = models.FloatField(default=0.0)
    context_precision_score = models.FloatField(default=0.0)
    context_recall_score = models.FloatField(blank=True, null=True)
    source = models.CharField(max_length=128, default='self-labeled')
