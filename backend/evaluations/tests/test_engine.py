import pytest

from evaluations.engine import RAGEvaluatorEngine, score_answer_relevance, score_context_precision


class MockClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []
        self.failures = 0

    def generate_json(self, *, prompt, schema, model, temperature, prompt_version):
        self.calls.append({
            'prompt': prompt,
            'model': model,
            'temperature': temperature,
            'prompt_version': prompt_version,
        })
        if 'faithfulness' in prompt.lower():
            return self.responses.get('faithfulness', {
                'claims': [
                    {'claim': 'Paris is the capital of France.', 'label': 'supported'},
                    {'claim': 'Paris is the capital of Germany.', 'label': 'unsupported'},
                ]
            })
        if 'relevance' in prompt.lower():
            return self.responses.get('relevance', {'rating': 4})
        if 'context precision' in prompt.lower() or 'precision' in prompt.lower():
            return self.responses.get('precision', {
                'chunks': [
                    {'chunk_index': 0, 'relevant': True},
                    {'chunk_index': 1, 'relevant': False},
                    {'chunk_index': 2, 'relevant': True},
                ]
            })
        if 'context recall' in prompt.lower() or 'recall' in prompt.lower():
            return self.responses.get('recall', {'covered_statements': 1, 'total_statements': 2})
        raise AssertionError('Unexpected prompt')


def test_score_answer_relevance_normalizes_rubric():
    assert score_answer_relevance(5) == 1.0
    assert score_answer_relevance(3) == 0.5
    assert score_answer_relevance(1) == 0.0


def test_score_context_precision_is_rank_aware():
    chunks = [True, False, True]
    assert score_context_precision(chunks) == pytest.approx(0.6666666667)


def test_engine_scores_faithfulness_and_relevance():
    client = MockClient()
    engine = RAGEvaluatorEngine(llm_client=client, model='test-model', provider='openai', temperature=0)

    result = engine.evaluate_case(
        query='What is the capital of France?',
        retrieved_contexts=['Paris is the capital of France.', 'Paris is in Europe.', 'The Eiffel Tower is famous.'],
        llm_response='Paris is the capital of France and is in Europe.',
        ground_truth='Paris is the capital of France.',
    )

    assert 0 <= result['faithfulness_score'] <= 1
    assert 0 <= result['answer_relevance_score'] <= 1
    assert result['has_hallucination'] is True
    assert result['prompt_version']


def test_engine_retries_invalid_json_with_backoff():
    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def generate_json(self, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise ValueError('bad payload')
            return {
                'claims': [{'claim': 'Paris is the capital of France.', 'label': 'supported'}],
                'rating': 5,
                'chunks': [{'chunk_index': 0, 'relevant': True}],
                'covered_statements': 1,
                'total_statements': 1,
            }

    engine = RAGEvaluatorEngine(llm_client=FlakyClient(), model='test-model', provider='openai', temperature=0)
    result = engine.evaluate_case(
        query='What is the capital of France?',
        retrieved_contexts=['Paris is the capital of France.'],
        llm_response='Paris is the capital of France.',
        ground_truth='Paris is the capital of France.',
    )

    assert result['faithfulness_score'] == 1.0
    assert result['answer_relevance_score'] == 1.0


def test_engine_uses_cache_for_identical_inputs():
    client = MockClient()
    engine = RAGEvaluatorEngine(llm_client=client, model='test-model', provider='openai', temperature=0)

    first = engine.evaluate_case(
        query='Capital of France?',
        retrieved_contexts=['Paris is the capital of France.'],
        llm_response='Paris is the capital of France.',
    )
    second = engine.evaluate_case(
        query='Capital of France?',
        retrieved_contexts=['Paris is the capital of France.'],
        llm_response='Paris is the capital of France.',
    )

    assert first['faithfulness_score'] == second['faithfulness_score']
    assert len(client.calls) == 4
