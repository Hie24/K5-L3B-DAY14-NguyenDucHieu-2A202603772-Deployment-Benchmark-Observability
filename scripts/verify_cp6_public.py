"""Record public CP6 checks; credentials are read only from the environment."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    key = os.environ.get("AGENT_API_KEY", "")
    if not key or not base.startswith("https://"):
        raise SystemExit("HTTPS base URL and AGENT_API_KEY are required")
    checks = []
    for name, path, method, authenticated, expected in (
        ("health", "/health", "GET", False, 200),
        ("ready", "/ready", "GET", False, 200),
        ("ask_without_key", "/ask", "POST", False, 401),
        ("ask_with_key", "/ask", "POST", True, 200),
    ):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["X-API-Key"] = key
        payload = json.dumps({"question": "Reply with one short sentence: what is deployment?"}).encode() if method == "POST" else None
        request = urllib.request.Request(base + path, data=payload, headers=headers, method=method)
        started = time.perf_counter()
        try:
            response = urllib.request.urlopen(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        except (OSError, urllib.error.URLError):
            checks.append({"name": name, "status": None, "expected": expected, "passed": False, "error": "network_error"})
            continue
        with response:
            status = response.code
            body = json.loads(response.read(100000).decode())
            record = {"name": name, "method": method, "path": path, "status": status,
                      "expected": expected, "passed": status == expected,
                      "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                      "request_id": response.headers.get("X-Request-ID"), "body": body}
            if authenticated and status == 200:
                record["passed"] = (body.get("provider") == "groq"
                                    and body.get("model") == "openai/gpt-oss-20b"
                                    and bool(body.get("answer"))
                                    and body.get("usage", {}).get("source") == "groq_reported")
            checks.append(record)
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "base_url": base,
              "checks": checks, "passed": all(item["passed"] for item in checks),
              "note": "Live HTTPS checks. Key headers are omitted. Cost uses configured prices, not a billing invoice."}
    out = Path(__file__).resolve().parents[1] / "reports" / "cp6"
    out.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, ensure_ascii=True, indent=2)
    if key in serialized or os.environ.get("GROQ_API_KEY", "__absent__") in serialized:
        raise SystemExit("Refusing to write a response containing credentials")
    (out / "public-smoke.json").write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
