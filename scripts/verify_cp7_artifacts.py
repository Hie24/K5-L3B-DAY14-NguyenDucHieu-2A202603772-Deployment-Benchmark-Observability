"""Check submission artifacts and table values against the measured CP7 JSON."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "06-lab-complete/benchmark-observability/develop"
REPORT = (ROOT / "BENCHMARK_REPORT.md").read_text(encoding="utf-8")


def read(name):
    public = ROOT / "reports" / f"{name}.json"
    local = DEV / "reports" / f"{name}.json"
    assert public.read_bytes() == local.read_bytes(), f"Different report copies: {name}"
    return json.loads(public.read_text(encoding="utf-8"))


def matches_digest(path, expected):
    # Git checkout may translate LF/CRLF between Linux and Windows. Preserve
    # recorded measurement hashes, accepting only this newline conversion.
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    return expected in {hashlib.sha256(value).hexdigest() for value in
                        (raw, lf, lf.replace(b"\n", b"\r\n"))}


def main():
    manifest_commands = {}
    for phase in ("baseline", "tail", "fixed"):
        manifest = json.loads((ROOT / f"reports/cp7/{phase}-manifest.json").read_text(encoding="utf-8"))
        assert manifest["all_child_processes_stopped"]
        if phase != "baseline":
            assert manifest["completed"]
        for path, expected in manifest["sha256"].items():
            if not path.endswith("utils/mock_llm.py") or phase == "fixed":
                assert matches_digest(ROOT / path, expected), path
        manifest_commands.update({c["name"]: c for c in manifest["commands"] if c["kind"] == "measurement"})
    names = []
    for concurrency in (1, 10, 50, 100):
        name = f"load_v2_c{concurrency}"
        data = read(name)
        lat = data["latency_ms"]
        result = "PASS" if data["slo"]["passed"] else "FAIL p95"
        row = f"| {concurrency} | {data['rps']:.2f} | {lat['p50']:.1f} | {lat['p95']:.1f} | {lat['p99']:.1f} | {data['error_rate'] * 100:.2f}% | {result} |"
        assert row in REPORT, name
        names.append(name)
    for slow in ("0", "0.03", "0.1"):
        name = f"load_v2_slow_{slow}"
        data = read(name)
        lat = data["latency_ms"]
        label = "0.03 (mặc định)" if slow == "0.03" else slow
        assert f"| {label} | {lat['avg']:.1f} | {lat['p95']:.1f} | {lat['p99']:.1f} |" in REPORT, name
        assert data["concurrency"] == 20
        names.append(name)
    for name in names:
        data = read(name)
        assert data["total_requests"] == 300
        assert sum(data["status_codes"].values()) == 300
        assert set(data["status_codes"]) <= {"200", "503"}
        assert data["slo"]["p95_ms"] == 500 and data["slo"]["error_rate"] == 0.02
        assert manifest_commands[name]["exit_code"] == (0 if data["slo"]["passed"] else 1)
    evals = [read(name) for name in ("eval_v1", "eval_v2", "eval_v2_fixed")]
    assert [data["passed"] for data in evals] == [1, 21, 23]
    for data in evals:
        assert data["total"] == 23 and data["errors"] == 0
        assert not data["quality_gate"]["regressions"]
    for label, key, fmt in (("Avg tokens / câu", "avg_tokens", ".1f"),
                            ("Tổng cost (USD)", "total_cost_usd", ".6f"),
                            ("Cost / câu đúng (USD)", "cost_per_correct_usd", ".8f")):
        assert "| " + label + " | " + " | ".join(format(data[key], fmt) for data in evals) + " |" in REPORT, label
    final = evals[-1]
    assert final["accuracy"] == 1.0 and final["quality_gate"]["min_accuracy"] == 1.0
    assert final["quality_gate"]["passed"] and manifest_commands["eval_v2_fixed"]["exit_code"] == 0
    original_failures = {item["id"] for item in evals[1]["results"] if not item["passed"]}
    assert original_failures == {"security-02", "scaling-03"}
    negative = read("eval_v1_regression")
    assert len(negative["quality_gate"]["regressions"]) == 20
    assert not negative["quality_gate"]["passed"] and manifest_commands["eval_v1_regression"]["exit_code"] == 1
    protected = {
        "06-lab-complete/check_production_ready.py": "73e4a70c13ba1127ffd7fafe14d2b9f6ce6ec016dccafd8ca3d416cf8817268a",
        "06-lab-complete/benchmark-observability/develop/eval/golden_dataset.jsonl": "22e672344ef72779959f3cf480391cef247b2f8ce86415010ddea9b315e959ec",
    }
    for path, expected in protected.items():
        assert matches_digest(ROOT / path, expected), path
    print("PASS: 11 report pairs match; 7 x 300 requests; report tables match JSON;")
    print("final eval 23/23, 0 regressions, exit 0; negative gate 20 regressions, exit 1;")
    print("dataset/grader/source hashes intact; manifests confirm child cleanup.")


if __name__ == "__main__":
    main()
