from django.conf import settings
from django.db import models

from evaluations.ownership import get_default_owner_id


class BenchmarkRun(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    dataset = models.ForeignKey(
        'evaluations.BenchmarkDataset',
        related_name='benchmark_runs',
        on_delete=models.CASCADE,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='benchmark_runs',
        on_delete=models.CASCADE,
        default=get_default_owner_id,
    )
    judge_provider = models.CharField(max_length=50)
    judge_model = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    item_count = models.PositiveIntegerField(default=0)
    evaluated_count = models.PositiveIntegerField(default=0)
    metrics = models.JSONField(default=dict)
    disagreements = models.JSONField(default=list)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)