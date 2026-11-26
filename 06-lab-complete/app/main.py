"""Part 6 agent: authenticated, stateless, budgeted mock or Groq requests."""
from contextlib import asynccontextmanager
import logging
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost, release_budget
from app.logging_config import log_event
from app.llm import GroqFailure, generate_groq, provider_configured
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import MOCK_RESPONSES, ask as llm_ask


def estimate_tokens(text: str) -> int:
    """Deterministic mock accounting, not provider-reported token usage."""
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


MAX_MOCK_OUTPUT_TOKENS = max(
    estimate_tokens(answer)
    for choices in MOCK_RESPONSES.values() for answer in choices
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("startup", environment=settings.environment, provider=settings.llm_provider)
    try:
        yield
    finally:
        # Uvicorn owns SIGTERM and drains in-flight requests before lifespan
        # shutdown. Do not replace its signal handlers.
        r.close()
        log_event("shutdown")


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def observe_request(request: Request, call_next):
    started = time.perf_counter()
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = request.scope.get("route")
        log_event("http_request", request_id=request_id, method=request.method,
                  path=route.path if route else "unmatched", status=status,
                  ms=round((time.perf_counter() - started) * 1000, 3))


@app.exception_handler(RedisError)
async def storage_error(request: Request, exc: RedisError):
    log_event("storage_unavailable", level=logging.WARNING,
              request_id=request.state.request_id, error_type=type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "State storage unavailable"},
                        headers={"Retry-After": "1"})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log_event("request_failed", level=logging.ERROR,
              request_id=request.state.request_id, error_type=type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(..., min_length=1, max_length=2000, strict=True)
    user_id: str | None = Field(default=None, min_length=1, max_length=128, strict=True)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not settings.agent_api_key or not provider_configured() or not redis_healthy():
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    if settings.llm_provider == "mock":
        input_tokens = estimate_tokens(body.question)
        reservation = check_budget(input_tokens, MAX_MOCK_OUTPUT_TOKENS)
        try:
            answer = llm_ask(body.question)
        except Exception:
            release_budget(reservation)
            raise
        output_tokens = estimate_tokens(answer)
        model, usage_source = "mock", "mock_estimate"
    else:
        if not provider_configured():
            raise HTTPException(status_code=503, detail="Model provider is not configured")
        # Reserve the configured model's entire context as a conservative
        # upper bound, without guessing its tokenizer. Refund against real usage.
        reservation = check_budget(settings.groq_context_window_tokens,
                                   settings.groq_max_completion_tokens)
        try:
            result = generate_groq(body.question)
        except GroqFailure as exc:
            if exc.refundable:
                release_budget(reservation)
            log_event("llm_error", level=logging.WARNING, provider="groq", code=exc.code)
            raise HTTPException(status_code=503, detail="Model provider unavailable; please retry",
                                headers={"Retry-After": str(exc.retry_after)}) from None
        answer, model = result.text, result.model
        input_tokens, output_tokens = result.input_tokens, result.output_tokens
        usage_source = "groq_reported"
    cost = record_cost(input_tokens, output_tokens, reservation)
    log_event("llm_call", provider=settings.llm_provider, model=model, input_tokens=input_tokens,
              output_tokens=output_tokens, cost_usd=cost, usage_source=usage_source)
    if not answer:
        raise HTTPException(status_code=503, detail="Model returned an incomplete answer; please retry")
    return {
        "question": body.question,
        "answer": answer,
        "provider": settings.llm_provider,
        "model": model,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                  "cost_usd": cost, "source": usage_source, "cost_source": "configured_prices"},
    }
