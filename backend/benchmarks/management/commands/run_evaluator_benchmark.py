import json

from django.core.management.base import BaseCommand, CommandError

from benchmarks.service import run_benchmark
from evaluations.models import BenchmarkDataset


class Command(BaseCommand):
    help = 'Run the configured judge against a benchmark dataset.'

    def add_arguments(self, parser):
        parser.add_argument('--dataset-id', type=int)

    def handle(self, *args, **options):
        dataset_id = options['dataset_id']
        if dataset_id is None:
            dataset_id = BenchmarkDataset.objects.order_by('id').values_list('id', flat=True).first()
        if dataset_id is None:
            raise CommandError('No benchmark dataset found. Run seed_sample_benchmark first.')
        try:
            result = run_benchmark({'dataset_id': dataset_id})
        except (BenchmarkDataset.DoesNotExist, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, indent=2))