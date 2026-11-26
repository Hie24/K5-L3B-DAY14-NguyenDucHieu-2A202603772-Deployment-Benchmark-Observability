"""Run the supplied local CP7 tools in WSL, retaining measured evidence.

Run baseline BEFORE editing the KB, then fixed AFTER editing it.
Existing output is never overwritten. Only child processes started here are stopped.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "06-lab-complete/benchmark-observability/develop"
PYTHON = DEV / ".venv/bin/python"
EVIDENCE = ROOT / "reports/cp7"
REPORTS = DEV / "reports"
ENV = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
for name in list(ENV):
    if name.startswith("MOCK_") or name in {"AGENT_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "AGENT_URL", "AGENT_VERSION", "PORT", "LLM_MODEL"}:
        ENV.pop(name)
ENV.update(LLM_MODEL="mock-llm-small", MOCK_LATENCY_MS="120", MOCK_JITTER_MS="60",
           MOCK_SLOW_MS="1500", MOCK_ERROR_RATE="0.01", MOCK_RETRIEVAL_MS="20")
ACTIVE = []
COMMANDS = []


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop(child):
    process, log = child
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    log.close()
    ACTIVE.remove(child)


def start(version, slow, label):
    port = 8001 if version == "v1" else 8002
    with socket.socket() as probe:
        # The previous server may leave TIME_WAIT sockets after shutdown.
        # Still reject a live listener, while allowing Uvicorn to reuse the port.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
    env = dict(ENV, AGENT_VERSION=version, PORT=str(port), MOCK_SLOW_RATE=slow)
    log = (EVIDENCE / f"{label}-server.jsonl").open("x", encoding="utf-8")
    process = subprocess.Popen([str(PYTHON), "-B", "-u", "app.py"], cwd=DEV, env=env,
                               stdout=log, stderr=subprocess.STDOUT)
    child = process, log
    ACTIVE.append(child)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Agent startup failed: {label}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                health = json.load(response)
            if health.get("agent_version") == version:
                COMMANDS.append({"kind": "server", "label": label, "started_at_utc": now(),
                                 "version": version, "port": port, "mock_slow_rate": slow,
                                 "pid": process.pid, "mock_env": {k: v for k, v in env.items() if k.startswith("MOCK_")}})
                return child
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Agent readiness timed out: {label}")


def run(name, args, expected=None):
    output = REPORTS / f"{name}.json"
    public_copy = ROOT / "reports" / output.name
    if output.exists() or public_copy.exists():
        raise RuntimeError(f"Refusing to overwrite {output.name}")
    command = [str(PYTHON), "-B", *args, "--out", f"reports/{name}.json"]
    started = now()
    print(f"RUN {name}", flush=True)
    with (EVIDENCE / f"{name}.txt").open("x", encoding="utf-8") as transcript:
        completed = subprocess.run(command, cwd=DEV, env=ENV, stdout=transcript,
                                   stderr=subprocess.STDOUT, timeout=240)
    COMMANDS.append({"kind": "measurement", "name": name, "started_at_utc": started,
                     "finished_at_utc": now(), "command": [".venv/bin/python", "-B", *command[2:]],
                     "exit_code": completed.returncode})
    if not output.is_file():
        raise RuntimeError(f"No report written for {name}")
    data = json.loads(output.read_text(encoding="utf-8"))
    gate_passed = data.get("slo", data.get("quality_gate", {})).get("passed")
    if completed.returncode != (0 if gate_passed else 1):
        raise RuntimeError(f"Unexpected exit code for {name}")
    if expected is not None and completed.returncode != expected:
        raise RuntimeError(f"Unexpected gate result for {name}")
    if "total_requests" in data and (data["total_requests"] != 300 or any(s.startswith("conn_error") for s in data["status_codes"])):
        raise RuntimeError(f"Incomplete or disconnected load run: {name}")
    shutil.copyfile(output, public_copy)
    print(f"DONE {name}: exit={completed.returncode}", flush=True)


def metrics(label, port=8002):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=3) as response:
        (EVIDENCE / f"{label}-metrics.txt").write_bytes(response.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("baseline", "tail", "fixed"))
    args = parser.parse_args()
    if os.name != "posix" or Path(sys.prefix).resolve() != PYTHON.parent.parent.resolve():
        raise SystemExit("Use develop/.venv/bin/python in WSL to run this script")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    manifest_path = EVIDENCE / f"{args.phase}-manifest.json"
    if manifest_path.exists():
        raise SystemExit("This phase already has evidence; preserve it instead of overwriting")
    manifest = {"phase": args.phase, "started_at_utc": now(), "python": platform.python_version(),
                "os": platform.system(), "kernel": platform.release(), "logical_cpus": os.cpu_count(),
                "packages": {name: importlib.metadata.version(name) for name in ("fastapi", "uvicorn", "pydantic", "httpx", "prometheus-client")},
                "sha256": {str(path.relative_to(ROOT)): digest(path) for path in
                           (DEV / "app.py", DEV / "load_test.py", DEV / "eval/run_eval.py", DEV / "eval/golden_dataset.jsonl", DEV / "utils/mock_llm.py")},
                "commands": COMMANDS, "completed": False}
    try:
        if args.phase == "baseline":
            v1 = start("v1", "0.03", "v1-original")
            v2 = start("v2", "0.03", "v2-original")
            run("eval_v1", ["eval/run_eval.py", "--url", "http://localhost:8001"], expected=1)
            run("eval_v2", ["eval/run_eval.py", "--url", "http://localhost:8002", "--baseline", "reports/eval_v1.json"], expected=0)
            run("eval_v1_regression", ["eval/run_eval.py", "--url", "http://localhost:8001", "--baseline", "reports/eval_v2.json"], expected=1)
            stop(v1)
            for concurrency in (1, 10, 50, 100):
                run(f"load_v2_c{concurrency}", ["load_test.py", "--url", "http://localhost:8002", "--requests", "300", "--concurrency", str(concurrency)])
            metrics("v2-original")
            stop(v2)
        if args.phase in {"baseline", "tail"}:
            if args.phase == "tail" and not (REPORTS / "load_v2_c100.json").is_file():
                raise RuntimeError("The tail recovery phase requires completed concurrency runs")
            for slow in ("0", "0.03", "0.1"):
                child = start("v2", slow, f"v2-slow-{slow}")
                run(f"load_v2_slow_{slow}", ["load_test.py", "--url", "http://localhost:8002", "--requests", "300", "--concurrency", "20"])
                metrics(f"v2-slow-{slow}")
                stop(child)
        else:
            if not (REPORTS / "eval_v2.json").is_file():
                raise RuntimeError("Run the original v2 baseline before editing the KB")
            start("v2", "0.03", "v2-fixed")
            run("eval_v2_fixed", ["eval/run_eval.py", "--url", "http://localhost:8002", "--min-accuracy", "1.0", "--baseline", "reports/eval_v2.json"], expected=0)
            data = json.loads((REPORTS / "eval_v2_fixed.json").read_text(encoding="utf-8"))
            if data["passed"] != data["total"] or data["total"] != 23 or data["quality_gate"]["regressions"]:
                raise RuntimeError("Final v2 must pass all 23 questions without regression")
            metrics("v2-fixed")
        manifest["completed"] = True
    finally:
        for child in list(ACTIVE):
            stop(child)
        manifest["finished_at_utc"] = now()
        manifest["all_child_processes_stopped"] = not ACTIVE
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"FINISHED {args.phase}: processes cleaned up", flush=True)


if __name__ == "__main__":
    main()
