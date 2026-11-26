# Benchmark & Observability Report — Day 14

> CP7 và CP8 đã hoàn thành; toàn bộ số liệu dùng kết quả thực tế từ `load_test.py`, `eval/run_eval.py`, Locust headless, Prometheus, Grafana và Jaeger.
> Benchmark dùng mock offline của Part 7; các số chi phí dưới đây là mô phỏng, không phải hóa đơn Groq/Railway.

**Họ tên:** Nguyễn Đức Hiếu
**Ngày chạy:** 2026-11-26 (GMT+7).
**Môi trường:** Ubuntu 24.04 trong WSL2, Python 3.12.3, Intel Core i5-11400H @ 2.70GHz; WSL thấy 12 logical CPU và 8,173,404,160 byte RAM (7.61 GiB). Agent và client cùng chạy local; mỗi agent là một process Uvicorn. Dependencies riêng: FastAPI 0.115.0, Uvicorn 0.30.0, Pydantic 2.9.0, httpx 0.27.2, prometheus-client 0.26.0. Xem [môi trường và bằng chứng](reports/cp7/README.md).

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Giữ trải nghiệm phần lớn request nhanh; đúng ngưỡng mặc định của load_test.py |
| Error rate `/ask` | ≤ 2% | Cho phép một phần lỗi mock mặc định 1%, vẫn phát hiện suy giảm ổn định |
| Accuracy trên golden dataset | 100% sau sửa KB, không regression | Yêu cầu CP7: 23/23; baseline dùng gate mặc định ≥80% để thấy tiến bộ |

Mỗi lượt load có 300 request được tính, thêm 1 warm-up không tính; timeout 10 giây. Concurrency dùng slow rate 0.03. Ba lượt tail dùng concurrency 20, lần lượt slow rate 0/0.03/0.1; mỗi lượt đều restart v2. Các cấu hình còn lại giữ nguyên: model mock-llm-small, latency 120 ms, jitter 60 ms, slow thêm 1500 ms, error rate 0.01, retrieval 20 ms. Cấu hình chi tiết và exit code ở các manifest trong [reports/cp7](reports/cp7/README.md).

Latency của script chỉ tính response 200; error rate tính toàn bộ request. RPS tính tất cả request/giây. Số liệu là một lượt cho mỗi cấu hình, có random jitter/fault injection, nên chưa phải capacity cam kết cho cloud.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.66 | 191.2 | 219.3 | 1678.7 | 1.00% | PASS |
| 10 | 43.82 | 193.8 | 222.2 | 1694.2 | 1.00% | PASS |
| 50 | 94.81 | 235.7 | 345.2 | 1743.5 | 2.00% | PASS |
| 100 | 56.43 | 557.7 | 3224.3 | 3431.4 | 1.00% | FAIL p95 |

**Nhận xét:** RPS không tăng tuyến tính: từ 1 lên 10 gần gấp 10, nhưng lên 50 chỉ đạt 94.81 RPS; lên 100 còn 56.43 RPS và p95 vượt 3 giây. Concurrency tạo thêm request đang chờ, không tạo thêm CPU hay worker. Client và server dùng chung máy; scheduling, xử lý HTTP và JSON log đồng bộ đều có thể giới hạn throughput. Kết quả cho thấy suy giảm ở lượt tải 100, chưa đủ profiling để quy riêng cho CPU hoặc I/O. Không chạy lại để thay kết quả FAIL bằng số đẹp hơn.

Nguồn: [c1](reports/load_v2_c1.json), [c10](reports/load_v2_c10.json), [c50](reports/load_v2_c50.json), [c100](reports/load_v2_c100.json). Lượt c100 trả exit 1 vì p95, không phải mất kết nối; cả bốn lượt đều đủ 300 request.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 195.0 | 224.7 | 243.6 |
| 0.03 (mặc định) | 234.8 | 237.3 | 1706.6 |
| 0.1 | 316.3 | 1686.1 | 1705.3 |

**Nhận xét:** Từ slow rate 0 lên 0.03, p99 tăng từ 243.6 lên 1706.6 ms trong khi avg chỉ tăng 39.8 ms; p99 phát hiện nhóm chậm nhỏ sớm hơn p95. Ở 0.1, p95 tăng lên 1686.1 ms, nhưng avg vẫn chỉ 316.3 ms: SLO theo average sẽ che trải nghiệm chậm của một nhóm người dùng. P99 ở 0.03 và 0.1 gần nhau vì cả hai đã rơi vào nhóm bị cộng thêm 1500 ms. Error rate ba lượt lần lượt 1.33%, 1.00%, 0.33%; chỉ lượt 0.1 FAIL SLO do p95.

Nguồn: [slow 0](reports/load_v2_slow_0.json), [slow 0.03](reports/load_v2_slow_0.03.json), [slow 0.1](reports/load_v2_slow_0.1.json). Không suy ra tỉ lệ lỗi thay đổi theo slow rate từ mẫu random 300 request.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.00% (23/23) |
| Avg tokens / câu | 57.4 | 108.8 | 118.2 |
| Tổng cost (USD) | 0.000408 | 0.000758 | 0.000829 |
| Cost / câu đúng (USD) | 0.00040815 | 0.00003607 | 0.00003606 |
| Quality gate | FAIL, exit 1 (≥80%) | PASS, exit 0 (≥80%, baseline v1) | PASS, exit 0 (100%, baseline v2) |

Nguồn: [eval_v1.json](reports/eval_v1.json), [eval_v2.json](reports/eval_v2.json), [eval_v2_fixed.json](reports/eval_v2_fixed.json). Cả ba report có 0 câu bị lỗi HTTP sau retry. Script làm tròn tổng cost đến 6 chữ số thập phân; cost/câu đúng tính từ tổng chưa làm tròn nên có thể khác phép chia trên ô tổng đã hiển thị.

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | token; hết hạn; chữ ký | Thêm tài liệu với trigger jwt/api key: JWT chứa claims, có chữ ký và có thể đặt hết hạn; phân biệt API key, thu hồi/xoay vòng và chữ ký với mã hóa |
| scaling-03 | cpu; memory; custom metrics | Thêm tài liệu với trigger kubernetes/hpa/horizontal pod autoscaler: HPA thay đổi replica theo CPU, memory hoặc custom metrics và target/min/max |

Hai câu trên ban đầu đều score 0; sau sửa đều score 1.0, missing_keywords rỗng. Chỉ thêm hai entry trong [develop/utils/mock_llm.py](06-lab-complete/benchmark-observability/develop/utils/mock_llm.py); giữ nguyên dataset, scorer, script load/eval và mock Part 6. Các manifest ghi SHA-256 trước/sau để đối chiếu.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** V2 thêm retrieval nên prompt dài, token và tổng cost tăng, nhưng cost/câu đúng giảm mạnh so với v1. Sau sửa, token trung bình tăng 108.8 → 118.2, tổng cost tăng 0.000758 → 0.000829 USD, đổi lại sửa được cả hai câu và giữ 21 câu đã đúng. Cost/câu đúng gần như giữ nguyên. Retrieval thêm khoảng 20 ms theo cấu hình; latency còn có jitter và slow injection. Chỉ có 23 câu eval nên không dùng p95 eval để kết luận hiệu năng; load test ở mục 2 mới phục vụ mục đích đó.

Accuracy ở đây là keyword matching: một câu đạt khi chứa ít nhất 60% keyword, không chứng minh đúng ngữ nghĩa mọi câu hỏi thực tế.

### 3.1 Quality gate và cách chặn merge trong CI

Đã chạy v1 với baseline v2: [eval_v1_regression.json](reports/eval_v1_regression.json) ghi accuracy 4.35%, **20 regression**, gate FAIL; [transcript](reports/cp7/eval_v1_regression.txt) và [manifest](reports/cp7/baseline-manifest.json) xác nhận exit code **1**. Điều này cho thấy response 200/latency tốt chưa đủ đảm bảo chất lượng.

Trong CI, sau checkout và cài `develop/requirements.txt`, khởi động v2 ở cổng 8002, chờ `/health` thành công và chạy từ thư mục develop:

```bash
python eval/run_eval.py --url http://localhost:8002 \
  --min-accuracy 1.0 --baseline reports/eval_v2_fixed.json \
  --out reports/eval_ci.json
```

Giữ baseline đã được review trong Git. Chạy lệnh như một bước CI thông thường, không dùng `continue-on-error` hoặc `|| true`: exit 1 làm job thất bại khi accuracy dưới 100% hoặc có câu baseline đúng nay sai. Cấu hình branch protection yêu cầu job quality gate thành công trước merge; bước deploy phụ thuộc job này. Baseline không được tự cập nhật theo ứng viên trong cùng lần chạy. Với CI kiểm nội dung, có thể đặt MOCK_ERROR_RATE=0 để tránh lỗi hạ tầng mock làm nhiễu; các số đo thực tế trong báo cáo này vẫn giữ error rate mặc định 0.01. Đây là thiết kế CI đề xuất; chưa tuyên bố có workflow GitHub chạy trên remote.

Kết quả cuối đã chạy local bằng chính lệnh CP7 yêu cầu:

```text
Accuracy      : 100.0%  (23/23)
✨ Câu được cải thiện : 2
⚠️  Câu bị regression : 0
Quality gate (accuracy ≥ 100%, không regression): ✅ PASS
```

Output đầy đủ: [eval_v2_fixed.txt](reports/cp7/eval_v2_fixed.txt). Manifest ghi exit 0 và agent đã được dừng sau kiểm tra.

---

## 4. Observability stack (production)

Unit test alert rules (`promtool test rules /p/alert_rules_test.yml` trên image `prom/prometheus:v3.16.0`) đã chạy và trả `SUCCESS`. Để container `agent` nhận đúng package trong `/home/agent/.local` khi `HOME=/app`, đã bổ sung `ENV PYTHONUSERBASE=/home/agent/.local` trong [production/Dockerfile](06-lab-complete/benchmark-observability/production/Dockerfile).

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception` / error span): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Một ảnh trang Alerts của Prometheus với ít nhất 2 alert cùng **firing** (theo rubric K5): [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png) (ghi nhận 3 alert cùng firing: `LLMCostBurnRateHigh`, `AgentHighErrorRate`, `AgentInstanceDown`)

### 4.2 Thí nghiệm "phá hệ thống"

Các thí nghiệm chạy với tải Locust nền (~30 users, ramp-up 5) và 2 replica `agent`. Thời gian được đo từ lúc áp dụng thay đổi tới khi `GET /api/v1/alerts` của Prometheus chuyển sang `firing`:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | **80.2s** (pending tại 25.1s) | `Error rate` (Golden Signals), `Requests/s theo status code` (status `503`), `LLM calls theo kết quả` |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | **140.3s** (pending tại 20.0s) | `Latency p95` (Golden Signals), `Latency /ask — p50 / p95 / p99` (khoảng cách avg và p95/p99 tăng mạnh) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | **140.5s** (pending tại 20.0s) | `Cost burn rate (USD/giờ)`, `LLM cost (1h)`, `LLM latency p95 theo model` |
| D | `docker pause` 1 instance (`agent-2`) | `AgentInstanceDown` (`for: 30s`) | **40.1s** | `Instances up` (giảm 2 → 1), `Requests/s theo instance` (traffic dồn về 1 instance) |
| E | `AGENT_VERSION=v1` | Không có alert mới nào firing (lưu ý: `LLMCostBurnRateHigh` còn dư trong cửa sổ `5m` của thí nghiệm C, không phải do `v1`) | — | `Retrieval hit ratio (agent v2)` (mất/ngừng cập nhật), `Tokens/s` giảm, bảng `agent_info` đổi sang `version="v1"` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Alert hạ tầng chỉ đo availability, latency, HTTP 5xx và chi phí; khi agent trả lời sai hoặc mất bước retrieval nhưng vẫn trả HTTP 200 thì các chỉ số này vẫn xanh. Trong production cần kết hợp: (1) chạy **quality gate eval** trên golden dataset + baseline trong CI/CD trước khi deploy (chặn merge khi accuracy giảm hoặc có regression), (2) theo dõi metric đặc thù của RAG/AI như **retrieval hit ratio** (`agent_retrieval_hits_total`) và cảnh báo khi tụt bất thường, và (3) đánh giá chất lượng liên tục trên traffic thật qua **user feedback** (thumbs up/down, tỷ lệ hỏi lại) hoặc **LLM-as-a-judge** trên mẫu log.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được:

- `trace_id`: `24f4d90cd488cd82acc157c9b5effb5e`
- Tổng thời gian: `1719.7 ms` (theo log `http_request`; Jaeger hiển thị `1.7s`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1693.2 ms`, `98.46%` tổng thời gian; `agent.retrieve_context` mất `25.3 ms`)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T09:59:28.978787+00:00", "level": "INFO", "service": "observable-agent", "instance": "45d6ac4bfde2", "event": "llm_call", "trace_id": "24f4d90cd488cd82acc157c9b5effb5e", "span_id": "f98565843b16b5fa", "request_id": "5af3f3561050", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1693.2}
{"ts": "2026-11-26T09:59:28.979865+00:00", "level": "INFO", "service": "observable-agent", "instance": "45d6ac4bfde2", "event": "http_request", "trace_id": "24f4d90cd488cd82acc157c9b5effb5e", "span_id": "f98565843b16b5fa", "request_id": "5af3f3561050", "method": "POST", "route": "/ask", "status": 200, "ms": 1719.7}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu `Aggregated` từ [scale_1_stats.csv](benchmark-results/scale_1_stats.csv) và [scale_3_stats.csv](benchmark-results/scale_3_stats.csv) (chạy với `--no-deps` để giữ đúng số replica agent):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 63.86 | 190 | 270 | 1700 | 83 / 7824 (1.06%) |
| 3 | 63.70 | 190 | 220 | 1700 | 63 / 7875 (0.80%) |

(Riêng endpoint `POST /ask`: với 1 instance đạt `57.54 req/s`, `p95 = 280 ms`, `p99 = 1700 ms`, `83/7050` lỗi; với 3 instance đạt `57.97 req/s`, `p95 = 230 ms`, `p99 = 1700 ms`, `63/7166` lỗi.)

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance làm **p95 giảm nhẹ** (`270 → 220 ms` Aggregated; `280 → 230 ms` trên `/ask`), nhưng **RPS (~63.7–63.9 req/s) và p99 (`1700 ms`) gần như không đổi**. Nút thắt nằm ở hai chỗ: (1) phía **load generator**, 100 user với `wait_time = between(0.5, 2)` (trung bình ~1.47s/chu kỳ) chỉ tạo tối đa ~68 req/s nên 1 instance FastAPI/Uvicorn async chưa bị bão hòa; (2) phía **upstream LLM (`mock_llm`)**, độ trễ phần lớn đến từ lời gọi LLM (~120–200 ms bình thường và ~3% tail bị cộng 1500 ms thành ~1700 ms), nên thêm replica agent không thể rút ngắn tail latency của upstream LLM.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Tăng concurrency có thể làm throughput giảm và tail latency tăng; phải đo cả RPS lẫn p95/p99.
  2. HTTP 200 và SLO latency tốt không đảm bảo câu trả lời đúng; eval baseline phát hiện regression (cùng lý do alert hạ tầng không bắt được `AGENT_VERSION=v1`).
  3. Cost/câu đúng phản ánh giá trị tốt hơn cost/câu; và scale ngang nhiều instance không giảm được `p99` nếu nút thắt nằm ở upstream LLM latency.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

Với production thật, bổ sung metric/alert về chất lượng (retrieval hit ratio thấp, user feedback âm, eval định kỳ trên golden dataset), timeout/retry upstream LLM ở tầng cả agent lẫn load balancer (vì lỗi 504 ở Nginx không vào metric của agent), và theo dõi saturation/queue của worker.
