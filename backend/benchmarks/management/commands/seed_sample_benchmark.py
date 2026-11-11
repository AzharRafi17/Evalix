from django.core.management.base import BaseCommand
from django.db import transaction

from evaluations.models import BenchmarkDataset, BenchmarkItem


class Command(BaseCommand):
    help = 'Create a clearly labeled 30-item synthetic benchmark dataset.'

    @transaction.atomic
    def handle(self, *args, **options):
        dataset, _ = BenchmarkDataset.objects.get_or_create(
            name='Evalix synthetic sample benchmark',
            defaults={
                'description': 'Thirty generated reference-code cases for smoke-testing benchmark metrics.',
                'source': 'synthetic-sample',
                'is_sample': True,
            },
        )
        dataset.is_sample = True
        dataset.source = 'synthetic-sample'
        dataset.save(update_fields=['is_sample', 'source'])
        for index in range(30):
            reference = f'CODE-{index:03d}'
            is_hallucinated = index % 2 == 1
            answer = f'WRONG-{index:03d}' if is_hallucinated else reference
            BenchmarkItem.objects.update_or_create(
                dataset=dataset,
                query=f'What is the reference code for sample {index:03d}?',
                defaults={
                    'retrieved_contexts': [f'The reference code for sample {index:03d} is {reference}.'],
                    'llm_response': f'The reference code is {answer}.',
                    'ground_truth': f'The reference code is {reference}.',
                    'hallucination_label': is_hallucinated,
                    'faithfulness_score': 0.0 if is_hallucinated else 1.0,
                    'answer_relevance_score': 1.0,
                    'context_precision_score': 1.0,
                    'context_recall_score': 1.0,
                    'source': 'synthetic-sample',
                },
            )
        self.stdout.write(self.style.SUCCESS(f'Seeded {dataset.items.count()} sample items (dataset {dataset.pk}).'))