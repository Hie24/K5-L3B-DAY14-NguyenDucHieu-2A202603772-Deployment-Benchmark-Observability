"""Verify the real Part 6 Compose stack on a non-default port, then clean it up."""
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "06-lab-complete"
OUT = ROOT / "reports" / "cp5"
PROJECT = "k5-day14-cp5-compose"
key = secrets.token_urlsafe(32)
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
env = dict(os.environ, AGENT_API_KEY=key, PORT=str(port), ENVIRONMENT="staging")
for name in ("OPENAI_API_KEY", "GROQ_API_KEY", "REDIS_URL"):
    env.pop(name, None)
transcript = []
command = ["docker", "compose", "-p", PROJECT]


def run(args, timeout=180):
    transcript.append("$ " + shlex.join(args))
    result = subprocess.run(args, cwd=BASE, env=env, capture_output=True, text=True, timeout=timeout)
    transcript.extend([result.stdout, result.stderr, f"[exit code {result.returncode}]"])
    if result.returncode:
        raise RuntimeError("Command failed: " + shlex.join(args))
    return result.stdout.strip()


def request(path, data=None, auth=False):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["X-API-Key"] = key
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers,
                                 data=json.dumps(data).encode() if data is not None else None)
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        payload = json.loads(response.read())
        transcript.append(f"{req.get_method()} {path} -> {response.status} " + json.dumps(payload, ensure_ascii=False))
        return response.status, payload


assert not run(["docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}"]), "Project already exists"
try:
    try:
        run(command + ["up", "-d", "--build", "--wait", "--wait-timeout", "120"], timeout=900)
        health = request("/health")[0]
        ready = request("/ready")[0]
        unauthorized = request("/ask", {"question": "Hello"})[0]
        authorized, answer = request("/ask", {"question": "What is deployment?"}, auth=True)
        assert (health, ready, unauthorized, authorized) == (200, 200, 401, 200)
        assert answer["provider"] == "mock" and answer["answer"]
        uid = run(command + ["exec", "-T", "agent", "python", "-c", "import os; print(os.getuid())"])
        assert uid == "10001"
        pid1 = run(command + ["exec", "-T", "agent", "python", "-c",
                             "print(open('/proc/1/cmdline','rb').read().decode().replace(chr(0),' '))"])
        assert "uvicorn" in pid1 and str(port) in pid1
        assert run(command + ["exec", "-T", "redis", "redis-cli", "ping"]) == "PONG"
        image = run(command + ["images", "-q", "agent"])
        image_bytes = int(run(["docker", "image", "inspect", "--format", "{{.Size}}", image]))
        assert image_bytes < 500 * 1024 * 1024
        summary = {"passed": True, "port": port, "health": health, "ready": ready,
                   "missing_key": unauthorized, "valid_key": authorized, "uid": int(uid),
                   "pid1_uvicorn": True, "image_bytes": image_bytes, "image_mib": round(image_bytes / 1024**2, 3)}
    finally:
        run(command + ["ps", "-a"])
        run(command + ["logs", "--no-color", "--tail", "80"])
        run(command + ["down", "--volumes"])
finally:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "compose.txt").write_text("\n".join(transcript).replace(key, "<REDACTED>"), encoding="utf-8")
(OUT / "compose.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print("Compose PASS: " + json.dumps(summary))
