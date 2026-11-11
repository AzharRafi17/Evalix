import pytest
from django.core.cache import cache

from evaluations.engine import (
    ContextPrecisionVerdict,
    ContextRecallVerdict,
    FaithfulnessVerdict,
    RAGEvaluatorEngine,
    RelevanceVerdict,
    score_answer_relevance,
    score_context_precision,
)
from evaluations.llm_clients import LLMResponse


@pytest.fixture(autouse=True)
def clear_evaluation_cache():
    cache.clear()
    yield
    cache.clear()


class MockClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def generate_json(self, *, prompt, schema, model, temperature, prompt_version):
        self.calls.append({
            'prompt': prompt,
            'schema': schema,
            'model': model,
            'temperature': temperature,
            'prompt_version': prompt_version,
        })
        defaults = {
            FaithfulnessVerdict: {
                'claims': [
                    {'claim': 'Paris is the capital of France.', 'label': 'supported'},
                    {'claim': 'Paris is the capital of Germany.', 'label': 'unsupported'},
                ],
            },
            RelevanceVerdict: {'rating': 4},
            ContextPrecisionVerdict: {
                'chunks': [
                    {'chunk_index': 0, 'relevant': True},
                    {'chunk_index': 1, 'relevant': False},
                    {'chunk_index': 2, 'relevant': True},
                ],
            },
            ContextRecallVerdict: {'covered_statements': 1, 'total_statements': 2},
        }
        return self.responses.get(schema, defaults[schema])


def make_engine(client, **kwargs):
    temperature = kwargs.pop('temperature', 0)
    return RAGEvaluatorEngine(
        llm_client=client,
        model='test-model',
        provider='openai',
        temperature=temperature,
        **kwargs,
    )


def evaluate(engine, contexts=None, ground_truth='Paris is the capital of France.'):
    return engine.evaluate_case(
        query='What is the capital of France?',
        retrieved_contexts=contexts or [
            'Paris is the capital of France.',
            'Paris is in Europe.',
            'The Eiffel Tower is famous.',
        ],
        llm_response='Paris is the capital of France and is in Europe.',
        ground_truth=ground_truth,
    )


def test_score_answer_relevance_normalizes_rubric():
    assert score_answer_relevance(5) == 1.0
    assert score_answer_relevance(3) == 0.5
    assert score_answer_relevance(1) == 0.0


def test_score_context_precision_is_rank_aware():
    assert score_context_precision([True, False, True]) == pytest.approx(0.8333333333)


def test_engine_scores_all_metrics_with_exact_values():
    result = evaluate(make_engine(MockClient()))

    assert result['faithfulness_score'] == 0.5
    assert result['answer_relevance_score'] == 0.75
    assert result['context_precision_score'] == pytest.approx(0.8333333333)
    assert result['context_recall_score'] == 0.5
    assert result['has_hallucination'] is True
    assert result['cached'] is False
    assert result['prompt_version']


def test_all_chunks_irrelevant_scores_zero():
    client = MockClient({
        ContextPrecisionVerdict: {'chunks': [
            {'chunk_index': 0, 'relevant': False},
            {'chunk_index': 1, 'relevant': False},
        ]},
    })

    result = evaluate(make_engine(client), contexts=['A', 'B'], ground_truth=None)

    assert result['context_precision_score'] == 0.0


def test_no_claims_has_nullable_score_and_flag():
    client = MockClient({FaithfulnessVerdict: {'claims': []}})

    result = evaluate(make_engine(client), ground_truth=None)

    assert result['faithfulness_score'] is None
    assert result['has_hallucination'] is False
    assert result['details']['no_claims'] is True


def test_engine_retries_api_errors_with_zero_backoff():
    class FlakyClient:
        def __init__(self):
            self.calls = 0
            self.mock = MockClient({
                ContextPrecisionVerdict: {'chunks': [{'chunk_index': 0, 'relevant': True}]},
            })

        def generate_json(self, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise ValueError('bad payload')
            return self.mock.generate_json(**kwargs)

    client = FlakyClient()
    result = evaluate(make_engine(client, retry_backoff_seconds=0), contexts=['Paris is the capital of France.'])

    assert result['faithfulness_score'] == 0.5
    assert result['answer_relevance_score'] == 0.75
    assert client.calls == 6


def test_engine_retries_pydantic_invalid_verdict_with_zero_backoff():
    class InvalidThenValidClient:
        def __init__(self):
            self.calls = 0

        def generate_json(self, *, schema, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {'rating': 6}
            return {'rating': 5}

    client = InvalidThenValidClient()
    engine = make_engine(client, retry_backoff_seconds=0)
    verdict = engine._judge(
        'answer_relevance',
        {'query': 'q', 'retrieved_contexts': [], 'llm_response': 'a', 'ground_truth': None},
        RelevanceVerdict,
        {'tokens_in': 0, 'tokens_out': 0, 'latency_ms': 0},
    )

    assert verdict.rating == 5
    assert client.calls == 2


def test_retries_exhausted_raise_runtime_error_with_zero_backoff():
    class AlwaysInvalidClient:
        def __init__(self):
            self.calls = 0

        def generate_json(self, **kwargs):
            self.calls += 1
            raise ValueError('invalid response')

    client = AlwaysInvalidClient()
    engine = make_engine(client, max_retries=2, retry_backoff_seconds=0)

    with pytest.raises(RuntimeError, match='failed after 2 attempts'):
        engine._judge(
            'answer_relevance',
            {'query': 'q', 'retrieved_contexts': [], 'llm_response': 'a', 'ground_truth': None},
            RelevanceVerdict,
            {'tokens_in': 0, 'tokens_out': 0, 'latency_ms': 0},
        )

    assert client.calls == 2


def test_invalid_chunk_index_is_rejected():
    client = MockClient({
        ContextPrecisionVerdict: {'chunks': [{'chunk_index': 2, 'relevant': True}]},
    })
    engine = make_engine(client, max_retries=1, retry_backoff_seconds=0)

    with pytest.raises(RuntimeError, match='context_precision judge failed'):
        evaluate(engine, contexts=['Only one context'], ground_truth=None)


def test_zero_max_retries_is_not_replaced_by_default():
    client = MockClient()
    engine = make_engine(client, max_retries=0)

    assert engine.max_retries == 0
    with pytest.raises(RuntimeError, match='failed after 0 attempts'):
        engine._judge(
            'answer_relevance',
            {'query': 'q', 'retrieved_contexts': [], 'llm_response': 'a', 'ground_truth': None},
            RelevanceVerdict,
            {'tokens_in': 0, 'tokens_out': 0, 'latency_ms': 0},
        )
    assert client.calls == []


def test_cache_is_shared_across_engines_and_zeroes_usage_and_cost():
    class UsageClient(MockClient):
        def generate_json(self, **kwargs):
            response = super().generate_json(**kwargs)
            return LLMResponse(response, tokens_in=10, tokens_out=5, latency_ms=12)

    client = UsageClient()
    first = evaluate(make_engine(client))
    second = evaluate(make_engine(client))

    assert first['tokens_in'] == 40
    assert first['tokens_out'] == 20
    assert first['cached'] is False
    assert second['tokens_in'] == 0
    assert second['tokens_out'] == 0
    assert second['estimated_cost'] == 0.0
    assert second['cached'] is True
    assert second['latency_ms'] == 0
    assert len(client.calls) == 4


def test_temperature_is_part_of_cache_key():
    client = MockClient()
    evaluate(make_engine(client, temperature=0.0))
    second = evaluate(make_engine(client, temperature=0.7))

    assert second['cached'] is False
    assert len(client.calls) == 8
