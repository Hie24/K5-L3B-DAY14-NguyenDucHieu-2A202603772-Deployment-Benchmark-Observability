"""One Groq request per call; secrets and provider error bodies never reach logs."""
from dataclasses import dataclass
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
SYSTEM_PROMPT = "You are a helpful assistant for a deployment lab. Reply clearly and concisely in the language of the user's question."


class GroqFailure(Exception):
    def __init__(self, code: str, *, refundable: bool = False, retry_after: int = 1):
        super().__init__(code)
        self.code = code
        self.refundable = refundable
        self.retry_after = retry_after


@dataclass(frozen=True)
class ModelResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def provider_configured() -> bool:
    return settings.llm_provider == "mock" or bool(settings.groq_api_key)


def generate_groq(question: str) -> ModelResult:
    if not settings.groq_api_key:
        raise GroqFailure("provider_not_configured", refundable=True)
    payload = {
        "model": settings.groq_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": question}],
        "max_completion_tokens": settings.groq_max_completion_tokens,
        "temperature": 0.2,
        "stream": False,
    }
    if settings.groq_model.startswith("openai/gpt-oss-"):
        payload["reasoning_effort"] = "low"
    request = Request(
        GROQ_CHAT_URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + settings.groq_api_key,
                 "Content-Type": "application/json", "User-Agent": "day14-agent/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.groq_timeout_seconds) as response:
            raw = response.read(2_000_001)
    except HTTPError as exc:
        retry = exc.headers.get("Retry-After", "1") if exc.headers else "1"
        try:
            retry_after = max(1, min(60, int(retry)))
        except ValueError:
            retry_after = 1
        # Rejections before inference can be refunded. A 5xx or timeout may
        # have happened after inference, so keep that reservation conservatively.
        refundable = 400 <= exc.code < 500 and exc.code != 408
        code = "upstream_rate_limited" if exc.code == 429 else "upstream_rejected" if refundable else "upstream_unavailable"
        exc.close()
        raise GroqFailure(code, refundable=refundable, retry_after=retry_after) from None
    except (URLError, OSError, socket.timeout):
        raise GroqFailure("upstream_network_error") from None
    try:
        if len(raw) > 2_000_000:
            raise ValueError("Response too large")
        data = json.loads(raw)
        usage = data["usage"]
        input_tokens, output_tokens = usage["prompt_tokens"], usage["completion_tokens"]
        if type(input_tokens) is not int or type(output_tokens) is not int:
            raise ValueError("Invalid usage")
        if not 0 <= input_tokens <= settings.groq_context_window_tokens:
            raise ValueError("Input usage outside configured context window")
        if not 0 <= output_tokens <= settings.groq_max_completion_tokens:
            raise ValueError("Output usage outside requested maximum")
        if data["model"] != settings.groq_model:
            raise ValueError("Unexpected model")
        answer = data["choices"][0]["message"].get("content") or ""
        if not isinstance(answer, str):
            raise ValueError("Invalid answer")
        return ModelResult(answer.strip(), data["model"], input_tokens, output_tokens)
    except (KeyError, IndexError, TypeError, ValueError):
        raise GroqFailure("invalid_upstream_response") from None
