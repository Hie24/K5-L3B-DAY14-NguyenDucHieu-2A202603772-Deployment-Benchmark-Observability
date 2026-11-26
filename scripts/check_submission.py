"""Audit required submission artifacts; print paths, never credential values."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "https://agent-production-74381197.up.railway.app"
CHECKS = []


def check(label, passed, detail=None):
    CHECKS.append({"check": label, "passed": bool(passed), "detail": detail})
    print(f"{'PASS' if passed else 'FAIL'}: {label}" + (f" ({detail})" if detail else ""))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    docs = {name: (ROOT / name).read_text(encoding="utf-8-sig") for name in
            ("README.md", "MISSION_ANSWERS.md", "DEPLOYMENT.md", "BENCHMARK_REPORT.md")}
    check("submission documents", all(text.strip() for text in docs.values()))
    check("deployment URL and completed results", PUBLIC in docs["DEPLOYMENT.md"] and
          "Chưa có" not in docs["DEPLOYMENT.md"] and "Chưa chạy" not in docs["DEPLOYMENT.md"])
    part3 = docs["MISSION_ANSWERS.md"].split("## Part 3 Cloud Deployment", 1)[1].split("## Part 4", 1)[0]
    check("Part 3 Railway/Render comparison and Cloud Run", "Chưa thực hiện" not in part3 and
          all(word in part3 for word in ("waitFor", "Secret Manager", "DOCKERFILE", "envVars")))
    images = ("dashboard.png", "running.png", "test.png", "grafana-dashboard.png",
              "jaeger-slow-trace.png", "jaeger-error-trace.png", "prometheus-alert-firing.png")
    for name in images:
        path = ROOT / "screenshots" / name
        data = path.read_bytes() if path.is_file() else b""
        valid = data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) > 1000
        dimensions = struct.unpack(">II", data[16:24]) if valid else (0, 0)
        check(f"screenshot {name}", valid and min(dimensions) > 300, f"{dimensions[0]}x{dimensions[1]}")
    result = json.loads((ROOT / "reports/cp6/public-smoke.json").read_text(encoding="utf-8-sig"))
    check("live public API results", result["passed"] and result["base_url"] == PUBLIC and
          [item["status"] for item in result["checks"]] == [200, 200, 401, 200])
    check("live Groq usage", result["checks"][-1]["body"]["usage"]["source"] == "groq_reported")
    for phase in ("cp5", "cp6"):
        text = (ROOT / f"reports/{phase}/production-readiness.txt").read_text(encoding="utf-8-sig")
        check(f"{phase} full production checker evidence", "41/41 checks passed" in text and "PASS 12/12" in text)
    cp7 = subprocess.run([os.sys.executable, "-B", "scripts/verify_cp7_artifacts.py"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    check("CP7 JSON, tables, protected source hashes and gates", cp7.returncode == 0)
    for count in (1, 3):
        name = f"scale_{count}_stats.csv"
        path = ROOT / "benchmark-results" / name
        original = ROOT / "06-lab-complete/benchmark-observability/production/benchmark-results" / name
        check(f"Locust scale {count} copied output", path.read_bytes() == original.read_bytes())
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
        total = next(row for row in rows if row["Name"] == "Aggregated")
        failures, requests = int(total["Failure Count"]), int(total["Request Count"])
        row = (f"| {count} | {float(total['Requests/s']):.2f} | {total['50%']} | {total['95%']} | "
               f"{total['99%']} | {failures} / {requests} ({failures / requests * 100:.2f}%) |")
        check(f"Locust scale {count} table matches CSV", row in docs["BENCHMARK_REPORT.md"])
    for name in ("MISSION_ANSWERS.md", "DEPLOYMENT.md", "BENCHMARK_REPORT.md", "06-lab-complete/README.md", "reports/cp6/README.md", "reports/cp7/README.md"):
        path = ROOT / name
        text = path.read_text(encoding="utf-8-sig")
        missing = []
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in link or link.startswith("#"):
                continue
            target = (path.parent / link.split("#")[0].strip("<>")).resolve()
            if not target.exists():
                missing.append(link)
        check(f"local links {name}", not missing, ", ".join(missing) or None)
    files = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").decode().split("\0")
    secrets = [value.encode() for value in json.loads(os.environ.get("LAB_AUDIT_SECRETS_JSON", "[]")) if value]
    check("configured credentials supplied for in-memory secret scan", len(secrets) >= 3)
    patterns = re.compile(rb"gsk_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}")
    secret_paths, bad_env = [], []
    for name in filter(None, files):
        path = ROOT / name
        if not path.is_file():
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            bad_env.append(name)
        content = path.read_bytes()
        if any(value in content for value in secrets) or patterns.search(content):
            secret_paths.append(name)
    check("candidate files contain no real configured secrets/provider tokens", not secret_paths, ", ".join(secret_paths) or None)
    check("no real .env in candidate files", not bad_env, ", ".join(bad_env) or None)
    history = git("log", "--all", "-p", "--no-ext-diff", "--format=commit:%H")
    check("history contains no configured secrets/provider token patterns", not patterns.search(history) and
          not any(value in history for value in secrets))
    historic_env = git("log", "--all", "--format=", "--name-only", "--", "**/.env*", ".env*").decode().splitlines()
    check("history contains no real .env", all(Path(name).name == ".env.example" for name in historic_env if name.strip()))
    contacts = []
    phone_paths = []
    email = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone = re.compile(r"(?<![A-Za-z0-9])(?:\+84|0)[35789][0-9]{8}(?![A-Za-z0-9])")
    for path in [ROOT / name for name in docs] + [p for p in (ROOT / "reports").rglob("*") if p.is_file()]:
        if path.suffix.lower() in {".md", ".txt", ".json", ".jsonl", ".html", ".ndjson"}:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if email.search(text):
                contacts.append(str(path.relative_to(ROOT)))
            if phone.search(text):
                phone_paths.append(str(path.relative_to(ROOT)))
    check("submission prose/reports contain no email addresses", not contacts, ", ".join(contacts) or None)
    check("submission prose/reports contain no Vietnamese phone patterns", not phone_paths, ", ".join(phone_paths) or None)
    output = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "passed": all(item["passed"] for item in CHECKS), "checks": CHECKS,
              "notes": ["Presence/consistency audit plus configured-secret scan; screenshots were also visually reviewed.",
                        "Historical checker/CP7 runs are linked, not replaced by a static check.",
                        "LMS submission is performed by the student; technical self-review is not asserted on their behalf."]}
    (ROOT / "reports/submission-audit.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
