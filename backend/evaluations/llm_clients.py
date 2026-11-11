import json
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings


@dataclass
class LLMResponse:
    data: dict
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


class LLMRequestError(RuntimeError):
    def __init__(self, message, *, retryable=False, status_code=None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class BaseLLMClient(ABC):
    @abstractmethod
    def generate_json(self, *, prompt, schema, model, temperature, prompt_version):
        raise NotImplementedError

    @staticmethod
    def _request_json(url, payload, headers):
        request = Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={**headers, 'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            raise LLMRequestError(
                f'LLM request failed (HTTP {exc.code})',
                retryable=retryable,
                status_code=exc.code,
            ) from None
        except (TimeoutError, socket.timeout):
            raise LLMRequestError('LLM request timed out', retryable=True) from None
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise LLMRequestError('LLM request timed out', retryable=True) from None
            raise LLMRequestError('LLM network request failed') from None
        except json.JSONDecodeError:
            raise LLMRequestError('LLM returned invalid JSON') from None


class OpenAICompatibleClient(BaseLLMClient):
    def __init__(self, *, api_key=None, base_url=None):
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.base_url = (base_url or settings.OPENAI_BASE_URL).rstrip('/')

    def generate_json(self, *, prompt, schema, model, temperature, prompt_version):
        started = time.perf_counter()
        payload = self._request_json(
            f'{self.base_url}/chat/completions',
            {
                'model': model,
                'temperature': temperature,
                'response_format': {'type': 'json_object'},
                'messages': [{'role': 'user', 'content': prompt}],
            },
            {'Authorization': f'Bearer {self.api_key}'},
        )
        choice = payload['choices'][0]['message']['content']
        return LLMResponse(
            data=json.loads(choice),
            tokens_in=payload.get('usage', {}).get('prompt_tokens', 0),
            tokens_out=payload.get('usage', {}).get('completion_tokens', 0),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


class GeminiClient(BaseLLMClient):
    def __init__(self, *, api_key=None):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY

    def generate_json(self, *, prompt, schema, model, temperature, prompt_version):
        started = time.perf_counter()
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{quote(model, safe="")}:generateContent?key={quote(self.api_key, safe="")}'
        )
        payload = self._request_json(
            url,
            {
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {
                    'temperature': temperature,
                    'responseMimeType': 'application/json',
                },
            },
            {},
        )
        candidate = payload['candidates'][0]['content']['parts'][0]['text']
        usage = payload.get('usageMetadata', {})
        return LLMResponse(
            data=json.loads(candidate),
            tokens_in=usage.get('promptTokenCount', 0),
            tokens_out=usage.get('candidatesTokenCount', 0),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


def get_llm_client(provider=None):
    selected_provider = provider or settings.EVALUATOR_PROVIDER
    if selected_provider in {'openai', 'openai-compatible'}:
        return OpenAICompatibleClient()
    if selected_provider == 'gemini':
        return GeminiClient()
    raise ValueError(f'Unsupported evaluator provider: {selected_provider}')