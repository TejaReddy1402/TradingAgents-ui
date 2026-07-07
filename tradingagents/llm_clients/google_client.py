import re
import time
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_RETRY_DELAY_RE = re.compile(r"retryDelay.*?(\d+)s", re.IGNORECASE | re.DOTALL)
_MAX_RETRIES = 4
_MAX_WAIT_S = 120  # cap per-attempt wait so we don't hang forever


def _parse_retry_delay(exc: Exception) -> float:
    """Extract the suggested retry delay (seconds) from a Google 429 error string."""
    m = _RETRY_DELAY_RE.search(str(exc))
    if m:
        return min(float(m.group(1)) + 2, _MAX_WAIT_S)
    return 30.0  # conservative default if header absent


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output and 429 retry.

    Gemini 3 models return content as list of typed blocks; normalizes to
    string for consistent downstream handling.

    Also retries on RESOURCE_EXHAUSTED (429) using the retryDelay hint
    embedded in the error response, which handles per-minute quota spikes
    without burdening the caller.  Daily-quota exhaustion (limit=20 on the
    free tier) cannot be resolved by retrying and surfaces immediately after
    _MAX_RETRIES attempts with a clearer message.
    """

    def invoke(self, input, config=None, **kwargs):
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return normalize_content(super().invoke(input, config, **kwargs))
            except Exception as exc:
                msg = str(exc)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    delay = _parse_retry_delay(exc)
                    last_exc = exc
                    if attempt < _MAX_RETRIES - 1:
                        print(
                            f"[google_client] 429 rate-limit hit; "
                            f"waiting {delay:.0f}s before retry "
                            f"(attempt {attempt + 1}/{_MAX_RETRIES - 1})…"
                        )
                        time.sleep(delay)
                        continue
                raise
        raise last_exc  # type: ignore[misc]


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "temperature", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Unified api_key maps to provider-specific google_api_key
        google_api_key = self.kwargs.get("api_key") or self.kwargs.get("google_api_key")
        if google_api_key:
            llm_kwargs["google_api_key"] = google_api_key

        # thinking_level is only supported on Gemini 3.x models.
        # Gemini 2.x uses thinking_budget (int) via a different API; passing
        # thinking_level to those models raises INVALID_ARGUMENT 400.
        thinking_level = self.kwargs.get("thinking_level")
        model_lower = self.model.lower()
        _is_thinking_level_model = (
            model_lower.startswith("gemini-3") or
            ("pro" in model_lower and not model_lower.startswith("gemini-2"))
        )
        if thinking_level and _is_thinking_level_model:
            if "pro" in model_lower and thinking_level == "minimal":
                thinking_level = "low"
            llm_kwargs["thinking_level"] = thinking_level

        return NormalizedChatGoogleGenerativeAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
