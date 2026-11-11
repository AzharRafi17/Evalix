from math import sqrt

from django.conf import settings

from evaluations.engine import RAGEvaluatorEngine
from evaluations.llm_clients import get_llm_client
from evaluations.models import BenchmarkDataset


SCORE_FIELDS = (
    ('faithfulness_score', 'faithfulness_score'),
    ('answer_relevance_score', 'answer_relevance_score'),
    ('context_precision_score', 'context_precision_score'),
    ('context_recall_score', 'context_recall_score'),
)


def _rank(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average_rank = ((start + 1) + end) / 2
        for index in order[start:end]:
            ranks[index] = average_rank
        start = end
    return ranks


def _correlation(left, right):
    if len(left) < 2:
        return None
    left_ranks = _rank(left)
    right_ranks = _rank(right)
    left_mean = sum(left_ranks) / len(left_ranks)
    right_mean = sum(right_ranks) / len(right_ranks)
    covariance = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left_ranks, right_ranks)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left_ranks)
    right_variance = sum((value - right_mean) ** 2 for value in right_ranks)
    denominator = sqrt(left_variance * right_variance)
    return covariance / denominator if denominator else None


def _classification_metrics(actual, predicted):
    true_positive = sum(a and p for a, p in zip(actual, predicted))
    true_negative = sum(not a and not p for a, p in zip(actual, predicted))
    false_positive = sum(not a and p for a, p in zip(actual, predicted))
    false_negative = sum(a and not p for a, p in zip(actual, predicted))
    count = len(actual)
    accuracy = (true_positive + true_negative) / count if count else 0.0
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    actual_positive = sum(actual) / count if count else 0.0
    predicted_positive = sum(predicted) / count if count else 0.0
    expected_agreement = (
        actual_positive * predicted_positive
        + (1 - actual_positive) * (1 - predicted_positive)
    )
    observed_agreement = accuracy
    kappa = (
        (observed_agreement - expected_agreement) / (1 - expected_agreement)
        if expected_agreement != 1 else 1.0
    )
    return {
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'cohens_kappa': kappa,
        'confusion_matrix': {
            'true_positive': true_positive,
            'true_negative': true_negative,
            'false_positive': false_positive,
            'false_negative': false_negative,
        },
        'count': count,
    }


def run_benchmark(judge_config):
    dataset = BenchmarkDataset.objects.get(pk=judge_config['dataset_id'])
    items = list(dataset.items.order_by('id'))
    if not items:
        raise ValueError('Benchmark dataset contains no items')

    provider = judge_config.get('provider', settings.EVALUATOR_PROVIDER)
    model = judge_config.get('model', settings.EVALUATOR_MODEL)
    prompt_version = judge_config.get('prompt_version', settings.EVALUATOR_PROMPT_VERSION)
    engine = judge_config.get('engine') or RAGEvaluatorEngine(
        llm_client=get_llm_client(provider),
        provider=provider,
        model=model,
        prompt_version=prompt_version,
    )
    actual_hallucinations = []
    predicted_hallucinations = []
    score_pairs = {field: ([], []) for field, _ in SCORE_FIELDS}
    disagreements = []
    evaluated_count = 0

    for item in items:
        try:
            result = engine.evaluate_case(
                query=item.query,
                retrieved_contexts=item.retrieved_contexts,
                llm_response=item.llm_response,
                ground_truth=item.ground_truth,
            )
        except Exception as exc:
            disagreements.append({
                'item_id': item.pk,
                'query': item.query,
                'error': str(exc)[:1000],
                'disagreement': 1.0,
            })
            continue

        evaluated_count += 1
        actual = item.hallucination_label
        predicted = bool(result['has_hallucination'])
        actual_hallucinations.append(actual)
        predicted_hallucinations.append(predicted)
        faithfulness = result.get('faithfulness_score')
        disagreement = abs(float(actual) - (1.0 - faithfulness)) if faithfulness is not None else float(actual != predicted)
        if actual != predicted:
            disagreements.append({
                'item_id': item.pk,
                'query': item.query,
                'human_hallucination': actual,
                'predicted_hallucination': predicted,
                'faithfulness_score': faithfulness,
                'disagreement': max(disagreement, 1.0),
            })
        for result_field, item_field in SCORE_FIELDS:
            human_score = getattr(item, item_field)
            predicted_score = result.get(result_field)
            if human_score is not None and predicted_score is not None:
                score_pairs[result_field][0].append(float(human_score))
                score_pairs[result_field][1].append(float(predicted_score))

    score_metrics = {}
    for field, (human_scores, judge_scores) in score_pairs.items():
        score_metrics[field] = {
            'spearman_correlation': _correlation(human_scores, judge_scores),
            'mean_absolute_error': (
                sum(abs(human - judged) for human, judged in zip(human_scores, judge_scores)) / len(human_scores)
                if human_scores else None
            ),
            'count': len(human_scores),
        }

    hallucination_metrics = _classification_metrics(
        actual_hallucinations,
        predicted_hallucinations,
    )
    return {
        'dataset_id': dataset.pk,
        'dataset_name': dataset.name,
        'item_count': len(items),
        'evaluated_count': evaluated_count,
        'failed_count': len(items) - evaluated_count,
        'hallucination_detection': hallucination_metrics,
        'score_metrics': score_metrics,
        'accuracy_target': 0.85,
        'accuracy_target_met': hallucination_metrics['accuracy'] >= 0.85,
        'worst_disagreements': sorted(
            disagreements,
            key=lambda row: row['disagreement'],
            reverse=True,
        )[:10],
    }