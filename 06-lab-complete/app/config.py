"""Environment configuration; injected variables take precedence over .env."""
from dataclasses import dataclass, field
from decimal import Decimal
import math
import os
from pathlib import Path
import re

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""), repr=False)
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"), repr=False)
    redis_key_prefix: str = field(default_factory=lambda: os.getenv("REDIS_KEY_PREFIX", "day14:agent"))
    redis_connect_timeout: float = field(default_factory=lambda: float(os.getenv("REDIS_CONNECT_TIMEOUT_SECONDS", "1")))
    redis_socket_timeout: float = field(default_factory=lambda: float(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "1")))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))
    daily_budget_usd: Decimal = field(default_factory=lambda: Decimal(os.getenv("DAILY_BUDGET_USD", "1")))
    monthly_budget_usd: Decimal = field(default_factory=lambda: Decimal(os.getenv("MONTHLY_BUDGET_USD", "10")))
    price_input_per_1k: Decimal = field(default_factory=lambda: Decimal(os.getenv("PRICE_INPUT_PER_1K_USD", "0.00015")))
    price_output_per_1k: Decimal = field(default_factory=lambda: Decimal(os.getenv("PRICE_OUTPUT_PER_1K_USD", "0.0006")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "mock").lower())
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""), repr=False)
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
    groq_max_completion_tokens: int = field(default_factory=lambda: int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "512")))
    groq_context_window_tokens: int = field(default_factory=lambda: int(os.getenv("GROQ_CONTEXT_WINDOW_TOKENS", "131072")))
    groq_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("GROQ_TIMEOUT_SECONDS", "5")))
    groq_price_input_per_1k: Decimal = field(default_factory=lambda: Decimal(os.getenv("GROQ_PRICE_INPUT_PER_1K_USD", "0.000075")))
    groq_price_output_per_1k: Decimal = field(default_factory=lambda: Decimal(os.getenv("GROQ_PRICE_OUTPUT_PER_1K_USD", "0.0003")))

    def __post_init__(self):
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        if self.rate_limit_per_minute < 1:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be positive")
        for value in (self.redis_connect_timeout, self.redis_socket_timeout):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Redis timeouts must be finite and positive")
        for value in (self.daily_budget_usd, self.monthly_budget_usd,
                      self.price_input_per_1k, self.price_output_per_1k,
                      self.groq_price_input_per_1k, self.groq_price_output_per_1k):
            if not value.is_finite() or not Decimal(0) <= value <= Decimal("1000000"):
                raise ValueError("Budgets and prices must be finite, nonnegative and at most 1000000")
        if not re.fullmatch(r"[A-Za-z0-9:_-]{1,64}", self.redis_key_prefix):
            raise ValueError("REDIS_KEY_PREFIX must contain 1-64 letters, digits, colon, underscore or dash")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported LOG_LEVEL")
        if self.llm_provider not in {"mock", "groq"}:
            raise ValueError("LLM_PROVIDER must be mock or groq")
        if not math.isfinite(self.groq_timeout_seconds) or not 0 < self.groq_timeout_seconds <= 5:
            raise ValueError("GROQ_TIMEOUT_SECONDS must be positive and at most 5 for the 8-second shutdown grace")
        if not 1 <= self.groq_max_completion_tokens <= min(65536, self.groq_context_window_tokens):
            raise ValueError("Invalid GROQ_MAX_COMPLETION_TOKENS")
        if not 1 <= self.groq_context_window_tokens <= 1000000:
            raise ValueError("Invalid GROQ_CONTEXT_WINDOW_TOKENS")
        if self.llm_provider == "groq" and self.groq_model != "openai/gpt-oss-20b":
            required = ("GROQ_PRICE_INPUT_PER_1K_USD", "GROQ_PRICE_OUTPUT_PER_1K_USD", "GROQ_CONTEXT_WINDOW_TOKENS")
            if not all(os.getenv(name) for name in required):
                raise ValueError("Changing GROQ_MODEL requires explicit prices and context-window configuration")


settings = Settings()
