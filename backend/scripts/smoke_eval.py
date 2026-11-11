import json
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django

django.setup()

from evaluations.engine import RAGEvaluatorEngine
from evaluations.llm_clients import get_llm_client


def main():
    engine = RAGEvaluatorEngine(llm_client=get_llm_client())
    result = engine.evaluate_case(
        query='What is the capital of France?',
        retrieved_contexts=[
            'Paris is the capital and most populous city of France.',
            'France is a country in Western Europe.',
        ],
        llm_response='Paris is the capital of France.',
        ground_truth='Paris is the capital of France.',
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
