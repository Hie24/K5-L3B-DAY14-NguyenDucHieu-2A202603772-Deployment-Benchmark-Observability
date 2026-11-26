"""Atomic global daily/monthly budgets using integer nano-USD in Redis.

Reserve the maximum possible request cost before calling the model, then refund
the unused portion. A hard process kill conservatively keeps its reservation
charged until the dated counter expires, rather than reopening that budget.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

UNITS_PER_USD = 1_000_000_000
RESERVE = """
local amount = tonumber(ARGV[1])
for i = 1, 2 do
    local used = tonumber(redis.call('GET', KEYS[i]) or '0')
    local limit = tonumber(ARGV[i + 1])
    if used >= limit or used + amount > limit then
        return {0, i}
    end
end
for i = 1, 2 do
    redis.call('INCRBY', KEYS[i], ARGV[1])
    redis.call('EXPIREAT', KEYS[i], ARGV[i + 3])
end
return {1, 0}
"""
SETTLE = """
local delta = tonumber(ARGV[1])
for i = 1, 2 do
    if tonumber(redis.call('GET', KEYS[i]) or '0') + delta < 0 then
        return redis.error_reply('Budget settlement would become negative')
    end
end
for i = 1, 2 do
    redis.call('INCRBY', KEYS[i], ARGV[1])
end
return 1
"""


@dataclass(frozen=True)
class BudgetReservation:
    keys: tuple[str, str]
    amount: int


def _period_keys(now: datetime | None = None) -> tuple[tuple[str, str], tuple[int, int]]:
    now = now or datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_day = midnight + timedelta(days=1)
    if now.month == 12:
        next_month = midnight.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = midnight.replace(month=now.month + 1, day=1)
    keys = (
        f"{settings.redis_key_prefix}:budget:day:{now:%Y-%m-%d}",
        f"{settings.redis_key_prefix}:budget:month:{now:%Y-%m}",
    )
    # Dated keys reset the active period; retain old keys an extra day so an
    # in-flight request crossing midnight can still settle its original keys.
    expires = (int((next_day + timedelta(days=1)).timestamp()),
               int((next_month + timedelta(days=1)).timestamp()))
    return keys, expires


def cost_units(input_tokens: int, output_tokens: int) -> int:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts must be nonnegative")
    if settings.llm_provider == "groq":
        input_price, output_price = settings.groq_price_input_per_1k, settings.groq_price_output_per_1k
    else:
        input_price, output_price = settings.price_input_per_1k, settings.price_output_per_1k
    usd = (input_tokens * input_price + output_tokens * output_price) / 1000
    return int((usd * UNITS_PER_USD).to_integral_value(rounding=ROUND_CEILING))


def check_budget(input_tokens: int = 0, output_tokens: int = 0) -> BudgetReservation:
    amount = cost_units(input_tokens, output_tokens)
    keys, expires = _period_keys()
    allowed, period = r.eval(
        RESERVE, 2, *keys, amount,
        int(settings.daily_budget_usd * UNITS_PER_USD),
        int(settings.monthly_budget_usd * UNITS_PER_USD), *expires,
    )
    if not allowed:
        name = "Daily" if period == 1 else "Monthly"
        raise HTTPException(status_code=402, detail=f"{name} budget exceeded")
    return BudgetReservation(keys=keys, amount=amount)


def record_cost(input_tokens: int, output_tokens: int,
                reservation: BudgetReservation | None = None) -> float:
    amount = cost_units(input_tokens, output_tokens)
    if reservation is None:
        check_budget(input_tokens, output_tokens)
    else:
        if amount > reservation.amount:
            raise ValueError("Model usage exceeded the reserved upper bound")
        r.eval(SETTLE, 2, *reservation.keys, amount - reservation.amount)
    return float(Decimal(amount) / UNITS_PER_USD)


def release_budget(reservation: BudgetReservation) -> None:
    """Refund a reservation when the mock model fails before producing usage."""
    r.eval(SETTLE, 2, *reservation.keys, -reservation.amount)
