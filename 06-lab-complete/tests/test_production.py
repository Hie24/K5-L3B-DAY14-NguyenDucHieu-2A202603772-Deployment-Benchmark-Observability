"""Integration checks beyond the supplied grader; uses its own temporary Redis."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

import redis

BASE = Path(__file__).resolve().parents[1]
REPORTS = BASE.parent / "reports" / ("cp6" if os.getenv("LAB_CHECKPOINT") == "cp6" else "cp5")
REPORTS.mkdir(parents=True, exist_ok=True)
DETAILS = {}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(url, data=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["X-API-Key"] = key
    payload = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, {key.lower(): value for key, value in response.headers.items()}, json.loads(response.read())


class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.redis_port = free_port()
        cls.container = "k5-day14-cp5-tests-" + secrets.token_hex(4)
        subprocess.run(["docker", "run", "-d", "--rm", "--name", cls.container,
                        "-p", f"127.0.0.1:{cls.redis_port}:6379", "redis:7-alpine"],
                       check=True, stdout=subprocess.DEVNULL)
        cls.redis_url = f"redis://127.0.0.1:{cls.redis_port}/0"
        cls.db = redis.from_url(cls.redis_url, decode_responses=True, socket_timeout=1)
        for _ in range(40):
            try:
                if cls.db.ping():
                    return
            except redis.RedisError:
                time.sleep(0.2)
        subprocess.run(["docker", "rm", "-f", cls.container], stdout=subprocess.DEVNULL)
        raise RuntimeError("Temporary test Redis did not start")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        subprocess.run(["docker", "rm", "-f", cls.container], check=True,
                       stdout=subprocess.DEVNULL)

    def env(self, **overrides):
        env = dict(os.environ)
        for name in ("OPENAI_API_KEY", "GROQ_API_KEY", "JWT_SECRET"):
            env.pop(name, None)
        env.update(AGENT_API_KEY=secrets.token_urlsafe(24), REDIS_URL=self.redis_url,
                   REDIS_KEY_PREFIX="cp5-test:" + secrets.token_hex(6),
                   ENVIRONMENT="staging", LOG_LEVEL="INFO", LLM_PROVIDER="mock", RATE_LIMIT_PER_MINUTE="1000",
                   DAILY_BUDGET_USD="1", MONTHLY_BUDGET_USD="10",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
        env.update(overrides)
        return env

    @contextmanager
    def server(self, label, env):
        port = free_port()
        lines = []
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host",
                                 "127.0.0.1", "--port", str(port), "--workers", "2", "--no-access-log"],
                                cwd=BASE, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, start_new_session=True)
        reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
        reader.start()
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    self.fail("Test server exited: " + "".join(lines)[-2000:])
                try:
                    if http(url + "/health")[0] == 200:
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                self.fail("Test server startup timed out")
            yield url, lines
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
            reader.join(timeout=3)
            raw = "".join(lines)
            safe = raw.replace(env["AGENT_API_KEY"], "<REDACTED>")
            (REPORTS / f"{label}-server.txt").write_text(safe, encoding="utf-8")

    def test_auth_validation_and_json_logs(self):
        env = self.env()
        statuses = []
        with self.server("validation", env) as (url, lines):
            self.assertEqual(http(url + "/ready")[0], 200)
            for key in (None, "wrong-demo-key", ""):
                statuses.append(http(url + "/ask", {"question": "Hello"}, key)[0])
            self.assertEqual(statuses, [401, 401, 401])
            invalid = [{}, {"question": ""}, {"question": "   "}, {"question": "x" * 2001},
                       {"question": 123}, {"question": "Hello", "extra": True}, b'{"question":']
            codes = [http(url + "/ask", body, env["AGENT_API_KEY"])[0] for body in invalid]
            self.assertEqual(codes, [422] * len(invalid))
            answer = http(url + "/ask", {"question": "private-question-marker", "user_id": "test"}, env["AGENT_API_KEY"])
            self.assertEqual(answer[0], 200)
            self.assertTrue(answer[2]["answer"])
        raw = "".join(lines)
        entries = [json.loads(line) for line in raw.splitlines() if line.startswith("{")]
        self.assertGreater(len(entries), 2)
        self.assertNotIn(env["AGENT_API_KEY"], raw)
        self.assertNotIn("private-question-marker", raw)
        DETAILS["validation"] = {"auth": statuses, "invalid_input": codes, "valid": 200,
                                 "json_log_records": len(entries), "no_key_or_question_in_logs": True}

    def test_atomic_rate_limit_restart_and_expired_window(self):
        env = self.env(RATE_LIMIT_PER_MINUTE="5")
        with self.server("rate", env) as (url, _):
            with ThreadPoolExecutor(max_workers=12) as pool:
                replies = list(pool.map(lambda _: http(url + "/ask", {"question": "Hello"}, env["AGENT_API_KEY"]), range(24)))
            codes = [reply[0] for reply in replies]
            self.assertEqual(codes.count(200), 5)
            self.assertEqual(codes.count(429), 19)
            self.assertTrue(all(int(reply[1]["retry-after"]) >= 1 for reply in replies if reply[0] == 429))
        with self.server("rate-restart", env) as (url, _):
            self.assertEqual(http(url + "/ask", {"question": "Hello"}, env["AGENT_API_KEY"])[0], 429)
            rate_key = self.db.keys(env["REDIS_KEY_PREFIX"] + ":rate:*")[0]
            self.db.delete(rate_key)
            seconds, micros = self.db.time()
            old = seconds * 1000 + micros // 1000 - 61_000
            self.db.zadd(rate_key, {f"expired-{i}": old for i in range(5)})
            self.assertEqual(http(url + "/ask", {"question": "Hello"}, env["AGENT_API_KEY"])[0], 200)
        DETAILS["rate"] = {"concurrent_requests": 24, "success": 5, "limited": 19,
                           "after_restart": 429, "after_expired_timestamps": 200, "workers": 2}

    def test_atomic_daily_budget_and_monthly_limit(self):
        env = self.env(DAILY_BUDGET_USD="0.0001", MONTHLY_BUDGET_USD="0.0001")
        with self.server("budget", env) as (url, _):
            with ThreadPoolExecutor(max_workers=12) as pool:
                replies = list(pool.map(lambda _: http(url + "/ask", {"question": "Hello"}, env["AGENT_API_KEY"]), range(24)))
            codes = [reply[0] for reply in replies]
            self.assertGreater(codes.count(200), 0)
            self.assertGreater(codes.count(402), 0)
            self.assertTrue(set(codes) <= {200, 402})
            balances = [int(self.db.get(key)) for key in self.db.keys(env["REDIS_KEY_PREFIX"] + ":budget:*")]
            self.assertEqual(len(balances), 2)
            self.assertTrue(all(0 <= amount <= 100_000 for amount in balances))
            self.assertEqual(balances[0], balances[1])
        monthly = self.env(DAILY_BUDGET_USD="1000", MONTHLY_BUDGET_USD="0")
        with self.server("monthly", monthly) as (url, _):
            response = http(url + "/ask", {"question": "Hello"}, monthly["AGENT_API_KEY"])
            self.assertEqual(response[0], 402)
            self.assertEqual(response[2]["detail"], "Monthly budget exceeded")
        DETAILS["budget"] = {"concurrent_requests": 24, "success": codes.count(200),
                             "blocked": codes.count(402), "daily_and_monthly_nano_usd": balances,
                             "limit_nano_usd": 100_000, "monthly_zero_status": 402}

    def test_redis_unavailable_fails_closed(self):
        env = self.env(REDIS_URL=f"redis://127.0.0.1:{free_port()}/0")
        with self.server("redis-down", env) as (url, _):
            health = http(url + "/health")[0]
            ready = http(url + "/ready")[0]
            ask = http(url + "/ask", {"question": "Hello"}, env["AGENT_API_KEY"])
            self.assertEqual((health, ready, ask[0]), (200, 503, 503))
            self.assertEqual(ask[2], {"detail": "State storage unavailable"})
        DETAILS["redis_down"] = {"health": health, "ready": ready, "ask": ask[0]}

    def test_budget_refund_and_period_boundary(self):
        code = '''
from datetime import datetime, timezone
from unittest.mock import patch
from app.main import AskRequest, ask
from app.config import settings
from app.cost_guard import _period_keys
from app.redis_client import r
with patch('app.main.llm_ask', side_effect=RuntimeError('synthetic model failure')):
    try:
        ask(AskRequest(question='Hello'), api_key=settings.agent_api_key)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Expected injected model failure')
keys, _ = _period_keys()
assert [int(r.get(key)) for key in keys] == [0, 0]
before, _ = _period_keys(datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
after, _ = _period_keys(datetime(2027, 1, 1, tzinfo=timezone.utc))
assert before[0] != after[0] and before[1] != after[1]
print('PASS: failed model call refunded both counters; UTC year/month/day keys roll over')
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=BASE, env=self.env(),
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        DETAILS["refund_and_rollover"] = {"refunded_daily": True, "refunded_monthly": True,
                                         "utc_day_month_year_boundary": True}

    def test_groq_pipeline_accounting_with_stub_http(self):
        code = '''
import io, json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from fastapi import HTTPException
from app.main import AskRequest, ask
from app.config import settings
from app.cost_guard import _period_keys, cost_units
from app.redis_client import r
payload={'model':settings.groq_model,'choices':[{'message':{'content':'Stub answer'}}],
         'usage':{'prompt_tokens':12,'completion_tokens':25}}
response=MagicMock()
response.__enter__.return_value.read.return_value=json.dumps(payload).encode()
with patch('app.llm.urlopen',return_value=response):
    result=ask(AskRequest(question='Hello'),api_key=settings.agent_api_key)
assert result['provider']=='groq' and result['usage']['source']=='groq_reported'
assert result['usage']['input_tokens']==12 and result['usage']['output_tokens']==25
assert result['usage']['cost_usd']==0.0000084
keys,_=_period_keys()
assert [int(r.get(key)) for key in keys]==[8400,8400]
error=HTTPError('https://api.groq.com',429,'sensitive-provider-message',{'Retry-After':'2'},io.BytesIO(b'not for logs'))
with patch('app.llm.urlopen',side_effect=error):
    try: ask(AskRequest(question='Hello'),api_key=settings.agent_api_key)
    except HTTPException as exc:
        assert exc.status_code==503 and exc.headers['Retry-After']=='2'
    else: raise AssertionError('Expected upstream rejection')
assert [int(r.get(key)) for key in keys]==[8400,8400]
with patch('app.llm.urlopen',side_effect=TimeoutError('sensitive-provider-message')):
    try: ask(AskRequest(question='Hello'),api_key=settings.agent_api_key)
    except HTTPException as exc: assert exc.status_code==503
    else: raise AssertionError('Expected upstream timeout')
reserved=cost_units(settings.groq_context_window_tokens,settings.groq_max_completion_tokens)
assert [int(r.get(key)) for key in keys]==[8400+reserved,8400+reserved]
print('PASS: STUBBED Groq usage settles real token fields; 429 refunds; ambiguous timeout holds reservation')
'''
        env = self.env(LLM_PROVIDER="groq", GROQ_API_KEY="unit-provider-key")
        result = subprocess.run([sys.executable, "-c", code], cwd=BASE, env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        DETAILS["groq_stub_pipeline"] = {"stubbed_http": True, "input_tokens": 12,
                                         "output_tokens": 25, "settled_nano_usd": 8400,
                                         "rejection_refunded": True, "timeout_reservation_held": True}


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProductionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"tests_run": result.testsRun, "successful": result.wasSuccessful(), "details": DETAILS}
    (REPORTS / "edge-cases.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if result.wasSuccessful() else 1)
