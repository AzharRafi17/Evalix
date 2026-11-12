import copy
import hashlib
import json
import time
from pathlib import Path
from time import sleep
from typing import Literal

from django.conf import settings
from django.core.cache import cache
from pydantic import BaseModel, Field

from evaluations.llm_clients import LLMRequestError, LLMResponse


class ClaimVerdict(BaseModel):
    claim: str
    label: Literal['supported', 'unsupported', 'contradicted']


class FaithfulnessVerdict(BaseModel):
    claims: list[ClaimVerdict] = Field(default_factory=list)
    reasoning: str = ''


class RelevanceVerdict(BaseModel):
    rating: int = Field(ge=1, le=5)
    reasoning: str = ''


class ChunkVerdict(BaseModel):
    chunk_index: int = Field(ge=0)
    relevant: bool


class ContextPrecisionVerdict(BaseModel):
    chunks: list[ChunkVerdict] = Field(default_factory=list)
    reasoning: str = ''


class ContextRecallVerdict(BaseModel):
    covered_statements: int = Field(ge=0)
    total_statements: int = Field(ge=0)
    reasoning: str = ''


def score_answer_relevance(rating):
    if not 1 <= rating <= 5:
        raise ValueError('Answer relevance rating must be between 1 and 5')
    return (rating - 1) / 4


def score_context_precision(relevant_chunks):
    """Return average precision over the ranked retrieved chunks."""
    relevant_total = sum(bool(relevant) for relevant in relevant_chunks)
    if not relevant_total:
        return 0.0
    relevant_seen = 0
    precision_sum = 0.0
    for rank, relevant in enumerate(relevant_chunks, start=1):
        if relevant:
            relevant_seen += 1
            precision_sum += relevant_seen / rank
    return precision_sum / relevant_total


class RAGEvaluatorEngine:
    METRICS = (
        ('faithfulness', FaithfulnessVerdict),
        ('answer_relevance', RelevanceVerdict),
        ('context_precision', ContextPrecisionVerdict),
        ('context_recall', ContextRecallVerdict),
    )

    def __init__(
        self,
        llm_client,
        model=None,
        provider=None,
        temperature=None,
        prompt_version=None,
        max_retries=None,
        retry_backoff_seconds=None,
    ):
        self.llm_client = llm_client
        self.model = model or settings.EVALUATOR_MODEL
        self.provider = provider or settings.EVALUATOR_PROVIDER
        self.temperature = settings.EVALUATOR_TEMPERATURE if temperature is None else temperature
        self.prompt_version = prompt_version or settings.EVALUATOR_PROMPT_VERSION
        self.max_retries = settings.EVALUATOR_MAX_RETRIES if max_retries is None else max_retries
        self.retry_backoff_seconds = (
            settings.EVALUATOR_RETRY_BACKOFF_SECONDS
            if retry_backoff_seconds is None else retry_backoff_seconds
        )
        self._prompt_root = Path(__file__).parent / 'prompts'

    def evaluate_case(self, *, query, retrieved_contexts, llm_response, ground_truth=None):
        cache_key = self._cache_key(query, retrieved_contexts, llm_response, ground_truth)
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            result = copy.deepcopy(cached_result)
            result.update({
                'tokens_in': 0,
                'tokens_out': 0,
                'latency_ms': 0,
                'estimated_cost': 0.0,
                'cached': True,
            })
            return result

        context = {
            'query': query,
            'retrieved_contexts': retrieved_contexts,
            'llm_response': llm_response,
            'ground_truth': ground_truth,
        }
        totals = {'tokens_in': 0, 'tokens_out': 0, 'latency_ms': 0}
        faithfulness = self._judge('faithfulness', context, FaithfulnessVerdict, totals)
        relevance = self._judge('answer_relevance', context, RelevanceVerdict, totals)
        precision = self._judge('context_precision', context, ContextPrecisionVerdict, totals)

        chunk_labels = [False] * len(retrieved_contexts)
        for verdict in precision.chunks:
            chunk_labels[verdict.chunk_index] = verdict.relevant

        claims = [claim.model_dump() for claim in faithfulness.claims]
        has_hallucination = any(claim.label != 'supported' for claim in faithfulness.claims)
        result = {
            'faithfulness_score': (
                sum(claim.label == 'supported' for claim in faithfulness.claims) / len(claims)
                if claims else None
            ),
            'answer_relevance_score': score_answer_relevance(relevance.rating),
            'context_precision_score': score_context_precision(chunk_labels),
            'context_recall_score': None,
            'has_hallucination': has_hallucination,
            'details': {
                'claims': claims,
                'no_claims': not claims,
                'context_chunks': [
                    {'chunk_index': index, 'relevant': relevant}
                    for index, relevant in enumerate(chunk_labels)
                ],
            },
            'reasoning': '\n'.join(filter(None, [
                faithfulness.reasoning,
                relevance.reasoning,
                precision.reasoning,
            ])),
            'prompt_version': self.prompt_version,
            'judge_provider': self.provider,
            'judge_model': self.model,
            'tokens_in': totals['tokens_in'],
            'tokens_out': totals['tokens_out'],
            'latency_ms': totals['latency_ms'],
            'cached': False,
        }

        if ground_truth:
            recall = self._judge('context_recall', context, ContextRecallVerdict, totals)
            if recall.covered_statements > recall.total_statements:
                raise ValueError('Covered ground-truth statements cannot exceed the total')
            result['context_recall_score'] = (
                recall.covered_statements / recall.total_statements
                if recall.total_statements else 0.0
            )
            result['details']['context_recall'] = recall.model_dump()
            result['reasoning'] = '\n'.join(filter(None, [result['reasoning'], recall.reasoning]))
            result['tokens_in'] = totals['tokens_in']
            result['tokens_out'] = totals['tokens_out']
            result['latency_ms'] = totals['latency_ms']

        result['estimated_cost'] = (
            (result['tokens_in'] + result['tokens_out'])
            * settings.EVALUATOR_COST_PER_1K_TOKENS / 1000
        )
        cache.set(cache_key, copy.deepcopy(result), timeout=None)
        return result

    def _judge(self, metric, context, schema, totals):
        prompt_path = self._prompt_root / self.prompt_version / f'{metric}.txt'
        prompt_template = prompt_path.read_text(encoding='utf-8')
        prompt = f'{prompt_template}\n\nInput JSON:\n{json.dumps(context, ensure_ascii=True)}'
        last_error = None
        for attempt in range(self.max_retries):
            started = time.perf_counter()
            try:
                response = self.llm_client.generate_json(
                    prompt=prompt,
                    schema=schema,
                    model=self.model,
                    temperature=self.temperature,
                    prompt_version=self.prompt_version,
                )
                if isinstance(response, LLMResponse):
                    data = response.data
                    totals['tokens_in'] += response.tokens_in
                    totals['tokens_out'] += response.tokens_out
                    totals['latency_ms'] += response.latency_ms
                else:
                    data = response
                    totals['latency_ms'] += round((time.perf_counter() - started) * 1000)
                data = self._normalize_response(metric, data, context)
                verdict = schema.model_validate(data)
                if metric == 'context_precision':
                    indexes = [item.chunk_index for item in verdict.chunks]
                    if sorted(indexes) != list(range(len(context['retrieved_contexts']))):
                        raise ValueError('Context precision must label every chunk exactly once')
                if metric == 'context_recall' and verdict.covered_statements > verdict.total_statements:
                    raise ValueError('Covered ground-truth statements cannot exceed the total')
                return verdict
            except Exception as exc:
                last_error = exc
                if isinstance(exc, LLMRequestError):
                    if exc.status_code == 429:
                        raise RuntimeError(
                            f'{metric} judge stopped after HTTP 429 rate limit; retry later'
                        ) from exc
                    retryable = exc.retryable
                else:
                    retryable = isinstance(exc, ValueError)
                if not retryable:
                    raise RuntimeError(
                        f'{metric} judge failed after {attempt + 1} attempt(s): {exc}'
                    ) from exc
                if attempt + 1 < self.max_retries:
                    sleep(self.retry_backoff_seconds * (2 ** attempt))
        raise RuntimeError(
            f'{metric} judge failed after {self.max_retries} attempts: {last_error}'
        ) from last_error

    @staticmethod
    def _normalize_response(metric, data, context):
        if metric != 'context_precision' or not isinstance(data, list):
            return data

        count = len(context['retrieved_contexts'])
        if len(data) == count and all(type(value) is bool for value in data):
            chunks = [
                {'chunk_index': index, 'relevant': relevant}
                for index, relevant in enumerate(data)
            ]
        elif len(data) == count and all(
            isinstance(value, dict)
            and set(value) == {'relevant'}
            and type(value['relevant']) is bool
            for value in data
        ):
            chunks = [
                {'chunk_index': index, 'relevant': value['relevant']}
                for index, value in enumerate(data)
            ]
        elif all(
            isinstance(value, dict)
            and {'chunk_index', 'relevant'} <= set(value)
            for value in data
        ):
            chunks = data
        else:
            return data
        return {'chunks': chunks, 'reasoning': ''}

    def _cache_key(self, query, retrieved_contexts, llm_response, ground_truth):
        payload = json.dumps(
            [
                query,
                retrieved_contexts,
                llm_response,
                ground_truth,
                self.provider,
                self.model,
                self.temperature,
                self.prompt_version,
            ],
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()