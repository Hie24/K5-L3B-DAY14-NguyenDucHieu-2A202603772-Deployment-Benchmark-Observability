# CP7 — Benchmark local và quality gate

Đã hoàn thành ngày 2026-11-26 (GMT+7), dùng agent mock độc lập trong `06-lab-complete/benchmark-observability/develop/`. Không gọi Railway/Groq. Báo cáo: [BENCHMARK_REPORT.md](../../BENCHMARK_REPORT.md), mục 1–3.

## Kết quả

- 7 lượt load test, mỗi lượt 300 request và 1 warm-up không tính: concurrency 1/10/50/100 và slow rate 0/0.03/0.1 ở concurrency 20.
- Concurrency 1/10/50 đạt SLO; concurrency 100 FAIL do p95 3224.3 ms. Slow rate 0/0.03 đạt; slow rate 0.1 FAIL do p95 1686.1 ms. Giữ nguyên các lượt FAIL và exit 1.
- Eval: v1 1/23, v2 ban đầu 21/23, v2 sửa KB 23/23, không regression, gate 100% PASS, exit 0.
- Negative gate: chạy v1 với baseline v2, phát hiện 20 regression và trả exit 1.
- Chỉ sửa hai entry knowledge base của mock trong develop: JWT/API key và Kubernetes HPA. Không sửa dataset, scorer, load test, app benchmark hoặc mock của Part 6.
- Các process do runner khởi động đều được dừng sau đo; không để server benchmark chiếm cổng 8001/8002.

## File nộp và bản sao

Mỗi JSON dưới đây tồn tại ở cả `../` (gốc `reports/`, theo SUBMISSION.md) và `../../06-lab-complete/benchmark-observability/develop/reports/`. Hai bản giống nhau từng byte. Các file `.txt` cùng tên tại thư mục này là output nguyên bản của script.

| JSON | Nội dung |
| --- | --- |
| [load_v2_c1.json](../load_v2_c1.json) | 300 request, concurrency 1 |
| [load_v2_c10.json](../load_v2_c10.json) | 300 request, concurrency 10 |
| [load_v2_c50.json](../load_v2_c50.json) | 300 request, concurrency 50 |
| [load_v2_c100.json](../load_v2_c100.json) | 300 request, concurrency 100; SLO FAIL |
| [load_v2_slow_0.json](../load_v2_slow_0.json) | Slow rate 0, concurrency 20 |
| [load_v2_slow_0.03.json](../load_v2_slow_0.03.json) | Slow rate 0.03, concurrency 20 |
| [load_v2_slow_0.1.json](../load_v2_slow_0.1.json) | Slow rate 0.1, concurrency 20; SLO FAIL |
| [eval_v1.json](../eval_v1.json) | Baseline v1, gate ≥80% FAIL |
| [eval_v2.json](../eval_v2.json) | V2 trước sửa KB, so với v1, gate ≥80% PASS |
| [eval_v2_fixed.json](../eval_v2_fixed.json) | V2 sau sửa, so với v2 cũ, gate 100% PASS |
| [eval_v1_regression.json](../eval_v1_regression.json) | Negative gate: v1 so với v2, FAIL |

## Bằng chứng hỗ trợ

- [baseline-manifest.json](baseline-manifest.json): cấu hình, SHA-256 source, phiên bản package, lệnh và exit code cho 3 eval đầu cùng 4 mức concurrency.
- [tail-manifest.json](tail-manifest.json): ba lượt slow rate và exit code.
- [fixed-manifest.json](fixed-manifest.json): SHA-256 sau sửa KB, eval cuối, exit 0.
- [dependencies-lock.txt](dependencies-lock.txt), [cpu.json](cpu.json), [memory.txt](memory.txt), [os-release.txt](os-release.txt): môi trường thực tế.
- Các file `*-server.jsonl`: stdout/stderr của agent; app ghi JSON, Uvicorn còn có dòng lifecycle dạng text.
- Các file `*-metrics.txt`: response thật từ `/metrics`, gồm counter HTTP, token, cost, histogram và agent_info.
- [knowledge-base.patch](knowledge-base.patch): diff hai entry được thêm.
- [initial-run-note.txt](initial-run-note.txt): lỗi của runner đã gặp và cách chạy tiếp mà không ghi đè kết quả.
- [artifact-verification.txt](artifact-verification.txt): đối chiếu 11 cặp report, 7 bảng số đo, eval/gate, SHA-256 và cleanup; tất cả đạt. Chạy lại từ gốc repo bằng `06-lab-complete/benchmark-observability/develop/.venv/bin/python -B scripts/verify_cp7_artifacts.py`.

Manifest baseline giữ `completed=false`: các phép đo concurrency/eval đã hoàn tất, nhưng bước kiểm cổng trước lượt tail đầu tiên bị `OSError: [Errno 98] Address already in use` ngay sau shutdown. Runner được sửa thêm `SO_REUSEADDR` cho socket probe để cho phép tái sử dụng cổng có socket cũ; phase `tail` hoàn thành phần còn lại. Hai manifest `tail` và `fixed` đều `completed=true`. Không sửa manifest cũ để biến lần chạy bị ngắt thành thành công.

## Chạy và tái lập

Đã dùng venv riêng của develop, không thay venv Part 6. Từ gốc repo trong WSL2:

```bash
cd 06-lab-complete/benchmark-observability/develop
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd ../../..
06-lab-complete/benchmark-observability/develop/.venv/bin/python -B scripts/run_cp7.py baseline
# Lần thực tế này chạy tiếp phase tail sau lỗi kiểm cổng đã ghi ở trên.
06-lab-complete/benchmark-observability/develop/.venv/bin/python -B scripts/run_cp7.py tail
# Sau khi thêm hai entry KB và restart v2:
06-lab-complete/benchmark-observability/develop/.venv/bin/python -B scripts/run_cp7.py fixed
```

`baseline` dùng source KB trước sửa; `fixed` dùng source sau sửa. Runner đã sửa sẽ chạy luôn phần tail trong phase baseline, nên chỉ dùng phase tail để khôi phục trường hợp baseline dừng trước phần đó. Runner từ chối ghi đè bằng chứng cũ. Để đo lại, dùng checkout/bộ output riêng hoặc chạy các lệnh gốc với tên output mới; random không seed nên không kỳ vọng số giống tuyệt đối. Source trước sửa có thể đối chiếu với commit gốc `83e677f` và patch KB.

Các lệnh gốc chạy từ develop, sau khi bật v1 ở cổng 8001/v2 ở 8002:

```bash
.venv/bin/python eval/run_eval.py --url http://localhost:8001 --out reports/eval_v1.json
.venv/bin/python eval/run_eval.py --url http://localhost:8002 --baseline reports/eval_v1.json --out reports/eval_v2.json
.venv/bin/python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json --out reports/eval_v1_regression.json
for c in 1 10 50 100; do
  .venv/bin/python load_test.py --url http://localhost:8002 --requests 300 --concurrency "$c" --out "reports/load_v2_c${c}.json"
done
# Restart v2 lần lượt với MOCK_SLOW_RATE=0, 0.03 và 0.1 trước mỗi lệnh tương ứng:
.venv/bin/python load_test.py --url http://localhost:8002 --requests 300 --concurrency 20 --out reports/load_v2_slow_0.json
.venv/bin/python load_test.py --url http://localhost:8002 --requests 300 --concurrency 20 --out reports/load_v2_slow_0.03.json
.venv/bin/python load_test.py --url http://localhost:8002 --requests 300 --concurrency 20 --out reports/load_v2_slow_0.1.json
# Sau sửa KB và restart v2:
.venv/bin/python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json
```

Đây là lệnh đã đo, không phải batch cần mọi lệnh trả 0: v1 và các trường hợp SLO/regression FAIL phải trả 1. Cách dùng exit code để chặn merge được giải thích ở mục 3.1 của báo cáo; chưa cấu hình branch protection hoặc chạy workflow remote.
