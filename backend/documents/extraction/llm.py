"""Groq chat-completions client (OpenAI-compatible API) with retries and safe errors.

* JSON mode + temperature 0 for deterministic, parseable output.
* Retries with exponential backoff on rate limits (429) and server errors (5xx).
* Errors never include the API key or request headers.
"""
import json
import logging
import re
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """The LLM call failed. ``retryable`` tells the caller whether trying again may help."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _parse_json(content: str) -> dict:
    text = (content or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise LLMError("The model did not return JSON.", retryable=True)
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError("The model returned invalid JSON.", retryable=True) from exc
    if not isinstance(value, dict):
        raise LLMError("The model returned JSON that is not an object.", retryable=True)
    return value


class GroqClient:
    def __init__(self, api_key: str, model: str, base_url: str, timeout: int = 60, max_retries: int = 3):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def complete_json(self, system: str, user: str) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(f"{self.base_url}/chat/completions", json=payload,
                                         headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = f"network error ({type(exc).__name__})"
                self._wait(attempt, None)
                continue

            status = response.status_code
            if status == 200:
                try:
                    content = response.json()["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise LLMError("The LLM response had an unexpected format.", retryable=True) from exc
                try:
                    return _parse_json(content)
                except LLMError as exc:
                    last_error = str(exc)
                    self._wait(attempt, None)
                    continue
            if status in (401, 403):
                raise LLMError("The LLM rejected the API key (check GROQ_API_KEY).", retryable=False)
            if status in (400, 404, 422):
                raise LLMError(f"The LLM rejected the request (HTTP {status}); check GROQ_MODEL.", retryable=False)
            if status == 429 or status >= 500:
                last_error = f"HTTP {status}"
                self._wait(attempt, response.headers.get("retry-after"))
                continue
            raise LLMError(f"Unexpected LLM response (HTTP {status}).", retryable=False)

        raise LLMError(f"The LLM did not succeed after {self.max_retries + 1} attempts ({last_error}).",
                       retryable=True)

    def _wait(self, attempt: int, retry_after: str | None) -> None:
        if attempt >= self.max_retries:
            return
        delay = 2 ** attempt
        if retry_after:
            try:
                delay = max(delay, min(float(retry_after), 30.0))
            except ValueError:
                pass
        logger.info("LLM retry %s/%s in %.1fs", attempt + 1, self.max_retries, delay)
        time.sleep(delay)


def get_llm_client() -> GroqClient | None:
    """Return a configured client, or None (rule-based extraction is used instead)."""
    api_key = getattr(settings, "GROQ_API_KEY", "").strip()
    model = getattr(settings, "GROQ_MODEL", "").strip()
    if not api_key or api_key.startswith("your-"):
        return None
    if not model or model.startswith("put-"):
        logger.warning("GROQ_API_KEY is set but GROQ_MODEL is not; using rule-based extraction.")
        return None
    return GroqClient(
        api_key=api_key,
        model=model,
        base_url=getattr(settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        timeout=int(getattr(settings, "LLM_TIMEOUT", 60)),
        max_retries=int(getattr(settings, "LLM_MAX_RETRIES", 3)),
    )
