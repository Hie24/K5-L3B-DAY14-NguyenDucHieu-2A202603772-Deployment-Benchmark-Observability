"""Groq adapter contract tests with stubbed HTTP, never live provider calls."""
from dataclasses import replace
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from app import llm
from app.config import settings
from app.cost_guard import cost_units


class GroqAdapterTests(unittest.TestCase):
    def setUp(self):
        self.config = replace(settings, llm_provider="groq", groq_api_key="unit-provider-key")
        self.config_patch = patch("app.llm.settings", self.config)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def payload(self):
        return {"model": self.config.groq_model, "choices": [{"message": {"content": "Answer"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 25}}

    def response(self, payload):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        return response

    def test_usage_and_request_parameters(self):
        with patch("app.llm.urlopen", return_value=self.response(self.payload())) as call:
            result = llm.generate_groq("Hello")
        req = call.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, llm.GROQ_CHAT_URL)
        self.assertEqual(body["model"], "openai/gpt-oss-20b")
        self.assertEqual(body["max_completion_tokens"], 512)
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual((result.input_tokens, result.output_tokens), (12, 25))
        self.assertEqual(call.call_count, 1)

    def test_upstream_rejection_refundable_and_safe(self):
        error = HTTPError(llm.GROQ_CHAT_URL, 429, "private-error", {"Retry-After": "120"}, io.BytesIO(b'private response'))
        with patch("app.llm.urlopen", side_effect=error):
            with self.assertRaises(llm.GroqFailure) as caught:
                llm.generate_groq("Hello")
        self.assertTrue(caught.exception.refundable)
        self.assertEqual(caught.exception.retry_after, 60)
        self.assertEqual(str(caught.exception), "upstream_rate_limited")

    def test_uncertain_failures_keep_reservation(self):
        failures = [TimeoutError("private-timeout"),
                    HTTPError(llm.GROQ_CHAT_URL, 500, "private-error", {}, io.BytesIO(b'private response'))]
        for failure in failures:
            with self.subTest(kind=type(failure).__name__), patch("app.llm.urlopen", side_effect=failure):
                with self.assertRaises(llm.GroqFailure) as caught:
                    llm.generate_groq("Hello")
                self.assertFalse(caught.exception.refundable)
                self.assertNotIn("private", str(caught.exception))

    def test_invalid_usage_rejected(self):
        for value in (-1, True, self.config.groq_max_completion_tokens + 1):
            payload = self.payload()
            payload["usage"]["completion_tokens"] = value
            with self.subTest(value=value), patch("app.llm.urlopen", return_value=self.response(payload)):
                with self.assertRaises(llm.GroqFailure):
                    llm.generate_groq("Hello")

    def test_empty_answer_keeps_usage_for_settlement(self):
        payload = self.payload()
        payload["choices"][0]["message"]["content"] = None
        with patch("app.llm.urlopen", return_value=self.response(payload)):
            result = llm.generate_groq("Hello")
        self.assertEqual(result.text, "")
        self.assertEqual(result.output_tokens, 25)

    def test_missing_key_never_calls_provider(self):
        with patch("app.llm.settings", replace(self.config, groq_api_key="")), patch("app.llm.urlopen") as call:
            self.assertFalse(llm.provider_configured())
            with self.assertRaises(llm.GroqFailure):
                llm.generate_groq("Hello")
        call.assert_not_called()

    def test_groq_prices_and_conservative_bound(self):
        with patch("app.cost_guard.settings", self.config):
            self.assertEqual(cost_units(12, 25), 8400)
            self.assertEqual(cost_units(131072, 512), 9984000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
