"""Run the supplied CP1-CP4 examples in WSL and save redacted evidence.

Usage from repository root: .venv/bin/python scripts/run_cp1_cp4.py cp1
Stages run sequentially because several examples use port 8000.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "cp1-cp4"
OUT.mkdir(parents=True, exist_ok=True)
PYTHON = str(ROOT / ".venv" / "bin" / "python")
SECRETS = ["sk-hardcoded-fake-key-never-do-this"]
ENV = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
for key in ("GROQ_API_KEY", "OPENAI_API_KEY", "AGENT_API_KEY", "JWT_SECRET"):
    ENV.pop(key, None)
ENV["PATH"] = str(ROOT / ".venv" / "bin") + os.pathsep + ENV["PATH"]
STAGE = ""


def redact(text):
    for secret in SECRETS:
        text = text.replace(secret, "<REDACTED>")
    text = re.sub(r'("(?:access_token|hint|password)"\s*:\s*")[^"]*', r'\1<REDACTED>', text)
    return re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "<REDACTED_JWT>", text)


def note(text):
    with (OUT / f"{STAGE}-transcript.txt").open("a", encoding="utf-8") as f:
        f.write(redact(text) + "\n")


def run(args, cwd=ROOT, check=True, timeout=120, env=None):
    note("$ " + shlex.join(map(str, args)))
    result = subprocess.run(args, cwd=cwd, env=env or ENV, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    note(result.stdout.rstrip() + f"\n[exit code {result.returncode}]\n")
    if check and result.returncode:
        raise RuntimeError(redact(f"Command failed: {shlex.join(map(str, args))}\n{result.stdout[-5000:]}"))
    return result.stdout


def curl(path, *, base="http://127.0.0.1:8000", data=None, headers=None, expected=200):
    args = ["curl", "--silent", "--show-error", "--max-time", "20", "-i", "-w", "\nCP_STATUS:%{http_code}\n"]
    if data is not None:
        args += ["-X", "POST", "-H", "Content-Type: application/json", "--data", json.dumps(data, ensure_ascii=False)]
    for key, value in (headers or {}).items():
        args += ["-H", f"{key}: {value}"]
    args += [base + path]
    output = run(args)
    raw, status_text = output.rsplit("CP_STATUS:", 1)
    status = int(status_text.strip())
    head, _, body = raw.strip().partition("\n\n")
    response_headers = dict(line.split(": ", 1) for line in head.splitlines()[1:] if ": " in line)
    try:
        response_body = json.loads(body)
    except json.JSONDecodeError:
        response_body = body
    result = {"status": status, "headers": response_headers, "body": response_body}
    assert status == expected, (path, expected, status, result["body"])
    return result


def wait_http(url, process=None, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process and process.poll() is not None:
            raise RuntimeError(f"Server exited with code {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    raise RuntimeError(f"Not ready: {url}")


def port_free(port):
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0, f"Port {port} is already occupied"


class Server:
    def __init__(self, folder, label, env=None, ready="/health"):
        self.folder, self.label, self.ready = folder, label, ready
        self.env = dict(ENV, **(env or {}))
        self.lines = []

    def __enter__(self):
        port_free(8000)
        note(f"$ cd {self.folder}; python app.py  # {self.label}")
        self.proc = subprocess.Popen([PYTHON, "app.py"], cwd=ROOT / self.folder, env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, start_new_session=True)
        self.reader = threading.Thread(target=lambda: self.lines.extend(self.proc.stdout), daemon=True)
        self.reader.start()
        try:
            wait_http("http://127.0.0.1:8000" + self.ready, self.proc)
        except Exception:
            self.stop()
            raise
        return self

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)
                note("Cleanup required SIGKILL for the process group")
        self.reader.join(timeout=3)
        (OUT / f"{self.label}-server.txt").write_text(redact("".join(self.lines)), encoding="utf-8")
        note(f"Server {self.label}: exit code {self.proc.returncode}")
        return self.proc.returncode

    def __exit__(self, *exc):
        self.stop()


def save_summary(result):
    (OUT / f"{STAGE}-summary.json").write_text(redact(json.dumps(result, ensure_ascii=False, indent=2)) + "\n", encoding="utf-8")
    print(STAGE + " PASS: " + redact(json.dumps(result, ensure_ascii=False)), flush=True)


def cp1():
    with Server("01-localhost-vs-production/develop", "cp1-develop", ready="/"):
        basic = curl("/ask?question=Hello", data={})
        mismatch = curl("/ask", data={"question": "Hello"}, expected=422)
        curl("/health", expected=404)
    with Server("01-localhost-vs-production/production", "cp1-production", env={"ENVIRONMENT": "staging", "DEBUG": "false"}):
        health = curl("/health")
        ready = curl("/ready")
        advanced = curl("/ask", data={"question": "What is deployment?"})
        curl("/ask", data={}, expected=422)
    save_summary({"develop": basic, "develop_json_mismatch": mismatch["status"],
                  "production_health": health, "production_ready": ready,
                  "production_ask": advanced})


def compose(folder, project, *args, **kwargs):
    return run(["docker", "compose", "-p", project, *args], cwd=ROOT / folder, **kwargs)


@contextlib.contextmanager
def stack(folder, project, scale=None):
    envfile = ROOT / folder / ".env.local"
    if not envfile.exists():
        envfile.touch()
    existing = compose(folder, project, "ps", "-a", "-q").strip()
    assert not existing, f"Project {project} already has containers; refusing to overwrite"
    args = ["up", "-d", "--build", "--wait", "--wait-timeout", "180"]
    if scale:
        args += ["--scale", f"agent={scale}"]
    try:
        compose(folder, project, *args, timeout=1800)
        yield
    finally:
        compose(folder, project, "ps", "-a", check=False)
        compose(folder, project, "logs", "--no-color", check=False)
        compose(folder, project, "down", "--volumes", check=False)


def cp2():
    port_free(8000)
    name = "k5-day14-cp2-basic"
    run(["docker", "run", "-d", "--name", name, "-p", "127.0.0.1:8000:8000", "my-agent:develop"])
    try:
        wait_http("http://127.0.0.1:8000/health")
        basic = curl("/ask?question=What%20is%20Docker%3F", data={})
        curl("/health")
        run(["docker", "logs", name])
    finally:
        run(["docker", "rm", "-f", name])
    port_free(80)
    port_free(443)
    folder, project = "02-docker/production", "k5-day14-docker"
    with stack(folder, project):
        wait_http("http://127.0.0.1/health")
        health = curl("/health", base="http://127.0.0.1")
        ready = curl("/ready", base="http://127.0.0.1")
        answer = curl("/ask", base="http://127.0.0.1", data={"question": "Explain microservices"})
        compose(folder, project, "exec", "-T", "agent", "id")
        compose(folder, project, "exec", "-T", "redis", "redis-cli", "ping")
    images = json.loads(run(["docker", "image", "inspect", "my-agent:develop", "my-agent:advanced"]))
    sizes = {item["RepoTags"][0]: item["Size"] for item in images}
    basic_size, advanced_size = images[0]["Size"], images[1]["Size"]
    save_summary({"basic_ask": basic, "nginx_health": health, "nginx_ready": ready,
                  "nginx_ask": answer, "sizes_bytes": sizes,
                  "develop_bytes": basic_size, "production_bytes": advanced_size,
                  "reduction_percent": (basic_size - advanced_size) / basic_size * 100})


def cp3():
    key, signing_key = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
    SECRETS.extend([key, signing_key])
    with Server("04-api-gateway/develop", "cp3-apikey", env={"AGENT_API_KEY": key}):
        missing = curl("/ask", data={"question": "Hello"}, expected=401)
        wrong = curl("/ask", data={"question": "Hello"}, headers={"X-API-Key": "incorrect-demo-key"}, expected=403)
        valid = curl("/ask", data={"question": "Hello"}, headers={"X-API-Key": key})
    with Server("04-api-gateway/production", "cp3-jwt", env={"JWT_SECRET": signing_key}):
        curl("/ask", data={"question": "Hello"}, expected=401)
        login = curl("/auth/token", data={"username": "student", "password": "demo123"})
        token = login["body"]["access_token"]
        SECRETS.append(token)
        headers = {"Authorization": "Bearer " + token}
        first = curl("/ask", data={"question": "Explain JWT"}, headers=headers)
        curl("/admin/stats", headers=headers, expected=403)
        statuses = [first["status"]]
        throttled = None
        for index in range(2, 21):
            expected = 200 if index <= 10 else 429
            response = curl("/ask", data={"question": f"Test {index}"}, headers=headers, expected=expected)
            statuses.append(response["status"])
            if response["status"] == 429:
                throttled = response
        usage = curl("/me/usage", headers=headers)
        teacher = curl("/auth/token", data={"username": "teacher", "password": "teach456"})
        teacher_token = teacher["body"]["access_token"]
        SECRETS.append(teacher_token)
        curl("/admin/stats", headers={"Authorization": "Bearer " + teacher_token})
    code = (
        "from cost_guard import CostGuard\n"
        "from fastapi import HTTPException\n"
        "guard=CostGuard(daily_budget_usd=0.000001)\n"
        "guard.check_budget('unit-demo')\n"
        "record=guard.record_usage('unit-demo',1000,1000)\n"
        "print('Synthetic module check: 1000 input + 1000 output tokens; cost USD',record.total_cost_usd)\n"
        "try: guard.check_budget('unit-demo')\n"
        "except HTTPException as exc:\n"
        " print('Per-user budget HTTP',exc.status_code); assert exc.status_code==402\n"
        "else: raise AssertionError('Cost guard did not block')\n"
    )
    run([PYTHON, "-c", code], cwd=ROOT / "04-api-gateway/production")
    save_summary({"missing_key": missing["status"], "wrong_key": wrong["status"],
                  "valid_key": valid["status"], "jwt_login": login["status"],
                  "jwt_ask": first["status"], "burst_statuses": statuses,
                  "throttled": throttled, "usage": usage,
                  "synthetic_cost_guard_status": 402})


def cp4():
    with Server("05-scaling-reliability/develop", "cp4-health") as server:
        health = curl("/health")
        ready = curl("/ready")
        holder = {}
        def request_during_shutdown():
            holder["response"] = curl("/ask?question=Long%20task", data={})
        thread = threading.Thread(target=request_during_shutdown)
        thread.start()
        time.sleep(0.05)
        started = time.monotonic()
        note("$ kill -TERM <owned-agent-pid>  # while POST /ask is in progress")
        server.proc.send_signal(signal.SIGTERM)
        thread.join(timeout=30)
        assert not thread.is_alive(), "In-flight request did not finish"
        server.proc.wait(timeout=30)
        elapsed = time.monotonic() - started
        assert holder["response"]["status"] == 200
        assert server.proc.returncode == 0, server.proc.returncode
        note(f"Graceful shutdown: in-flight HTTP 200, exit 0, {elapsed:.3f}s")
    folder, project = "05-scaling-reliability/production", "k5-day14-scaling"
    port_free(8080)
    with stack(folder, project, scale=3):
        wait_http("http://127.0.0.1:8080/health")
        provided = run([PYTHON, "test_stateless.py"], cwd=ROOT / folder)
        (OUT / "cp4-test-stateless.txt").write_text(provided, encoding="utf-8")
        session_id = re.search(r"Session ID: ([a-f0-9-]+)", provided).group(1)
        history = curl(f"/chat/{session_id}/history", base="http://127.0.0.1:8080")
        assert history["body"]["count"] == 10
        first = curl("/chat", base="http://127.0.0.1:8080", data={"question": "Before stopping an instance"})
        assert first["body"]["storage"] == "redis"
        backend = next(value for key, value in first["headers"].items() if key.lower() == "x-served-by")
        backend_ip = backend.split(":")[0]
        ids = compose(folder, project, "ps", "-q", "agent").split()
        stopped = None
        for container_id in ids:
            info = json.loads(run(["docker", "inspect", container_id]))[0]
            if any(net["IPAddress"] == backend_ip for net in info["NetworkSettings"]["Networks"].values()):
                stopped = container_id
                break
        assert stopped, "Could not map serving instance to its own container"
        run(["docker", "stop", "--time", "10", stopped])
        after = curl("/chat", base="http://127.0.0.1:8080", data={"question": "After stopping the serving instance", "session_id": first["body"]["session_id"]})
        assert after["body"]["served_by"] != first["body"]["served_by"]
        retained = curl(f"/chat/{first['body']['session_id']}/history", base="http://127.0.0.1:8080")
        assert retained["body"]["count"] == 4
        compose(folder, project, "stop", "redis")
        probe_code = (
            "import urllib.request, urllib.error\n"
            "statuses=[]\n"
            "for path in ('/health','/ready'):\n"
            " try:\n"
            "  response=urllib.request.urlopen('http://127.0.0.1:8000'+path, timeout=8)\n"
            " except urllib.error.HTTPError as exc: response=exc\n"
            " statuses.append(response.status)\n"
            " print(path,response.status,response.read().decode())\n"
            "assert statuses==[200,503],statuses\n"
        )
        for container_id in ids:
            if container_id != stopped:
                run(["docker", "exec", container_id, "python", "-c", probe_code], timeout=25)
        redis_down_health = curl("/health", base="http://127.0.0.1:8080")
        redis_down_ready = curl("/ready", base="http://127.0.0.1:8080", expected=503)
    save_summary({"develop_health": health, "develop_ready": ready,
                  "shutdown_inflight_status": holder["response"]["status"],
                  "shutdown_exit_code": server.proc.returncode, "shutdown_seconds": round(elapsed, 3),
                  "provided_history_count": history["body"]["count"],
                  "before_stop": first, "after_stop": after,
                  "history_after_stop": retained["body"]["count"],
                  "redis_down_health": redis_down_health, "redis_down_ready": redis_down_ready})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["cp1", "cp2", "cp3", "cp4"])
    args = parser.parse_args()
    STAGE = args.stage
    (OUT / f"{STAGE}-transcript.txt").write_text("Stage " + STAGE + "; actual commands and outputs; secrets redacted.\n\n", encoding="utf-8")
    globals()[STAGE]()
