# Day 14 Deployment Information

## Trạng thái và URL public

**Đã deploy agent Part 6 lên Railway, kết nối Redis nội bộ và gọi Groq thật.** Kiểm tra lại ngày 2026-11-26 lúc 17:33 (GMT+7): cả hai service SUCCESS; bốn phép thử public trả **200 / 200 / 401 / 200**.

- Public URL: **https://agent-production-74381197.up.railway.app**
- Swagger UI: https://agent-production-74381197.up.railway.app/docs
- Project: `k5-day14-agent`, environment `production`.
- Dashboard quản trị: https://railway.com/project/3685af52-7142-41e8-9212-edbe1dcd4609?environmentId=b2833bcb-4ad3-457b-88e8-c4964ed42909
- Agent deployment: `36643a81-fb3d-4eed-b459-af57b38503f7`.
- Redis deployment: `ba6196df-4c2d-4cb0-ab76-b79a53fd0a1f`.

Trạng thái đã lọc bỏ giá trị secret: [railway-state.json](reports/cp6/railway-state.json). Dùng gói trial; giữ service hoạt động tới khi được chấm.

## Source và cách triển khai thực tế

Agent nằm tại `06-lab-complete/`, build bằng Dockerfile multi-stage và chạy Uvicorn non-root, bind `0.0.0.0` theo PORT. Redis là service riêng trong cùng project; REDIS_URL tham chiếu `${{Redis.REDIS_URL}}`, không hardcode mật khẩu hoặc fallback state trong RAM.

Đã deploy bằng Railway CLI 5.75.0 từ gốc repo sau khi link project:

```bash
railway up 06-lab-complete --path-as-root --service agent --environment production --detach --json
railway domain --service agent --port 8000 --json
```

`--path-as-root` đặt nội dung Part 6 tại gốc archive upload: Dockerfile và railway.toml ở root, service Root Directory để `/`. Config dùng builder DOCKERFILE, healthcheck /health, timeout 60 giây, restart on failure tối đa 3 lần. /ready kiểm key, cấu hình provider và Redis; live /ask xác nhận key Groq gọi được model.

Nếu chuyển sang GitHub autodeploy, cần kết nối source repo, đặt Root Directory `/06-lab-complete` và đường dẫn config `/06-lab-complete/railway.toml`. Bản đang chạy là CLI upload, chưa cấu hình GitHub autodeploy.

## Bốn phép thử public

Trong WSL, đặt BASE bằng URL public và AGENT_API_KEY bằng key của **agent** lấy từ Railway Variables. Key này khác GROQ_API_KEY. Không ghi key trực tiếp vào lệnh được chụp ảnh hoặc commit.

```bash
BASE=https://agent-production-74381197.up.railway.app
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

Kết quả thật bằng [verify_cp6_public.py](scripts/verify_cp6_public.py) lúc `2026-11-26T10:33:04Z`; request có key hỏi một câu ngắn về deployment:

| Kiểm tra | Mong đợi | Thực tế | Thời gian client |
| --- | --- | --- | --- |
| GET /health | 200 | **200** | 548.23 ms |
| GET /ready | 200 | **200** | 656.75 ms |
| POST /ask thiếu key | 401 | **401** | 410.77 ms |
| POST /ask đúng key | 200 | **200** | 802.11 ms |

Response có `provider=groq`, `model=openai/gpt-oss-20b`, usage do Groq báo: **108 input / 30 output tokens**, `usage.source=groq_reported`. Cost estimate **0.00001710 USD** theo đơn giá cấu hình, không phải hóa đơn provider. Đây là kiểm thử chức năng một request; không dùng làm benchmark/SLO Groq.

Nguồn đầy đủ: [public-smoke.json](reports/cp6/public-smoke.json). Lần đầu giữ tại [public-smoke-initial.json](reports/cp6/public-smoke-initial.json). Headers chứa key không được lưu. Chạy lại từ gốc repo khi đã có AGENT_API_KEY trong environment:

```bash
06-lab-complete/.venv/bin/python scripts/verify_cp6_public.py --base "$BASE"
```

## Biến môi trường đã đặt

Chỉ liệt kê tên và vai trò, không công bố giá trị secret. Railway tự cấp thêm các biến RAILWAY_*.

| Biến | Vai trò |
| --- | --- |
| AGENT_API_KEY | Secret xác thực client qua X-API-Key |
| GROQ_API_KEY | Secret mới dùng gọi Groq |
| groq_lab14 | Tên biến ban đầu nhập trên dashboard; đã sao chép sang GROQ_API_KEY mà app đọc |
| REDIS_URL | Reference tới Redis nội bộ có xác thực |
| ENVIRONMENT, PORT, WEB_CONCURRENCY, LOG_LEVEL | Môi trường, cổng, số worker, logging |
| LLM_PROVIDER, GROQ_MODEL | Provider Groq và model production |
| GROQ_MAX_COMPLETION_TOKENS, GROQ_CONTEXT_WINDOW_TOKENS | Giới hạn output và context để reserve budget |
| GROQ_TIMEOUT_SECONDS | Timeout upstream phù hợp graceful shutdown |
| GROQ_PRICE_INPUT_PER_1K_USD, GROQ_PRICE_OUTPUT_PER_1K_USD | Đơn giá để estimate cost và budget |
| RATE_LIMIT_PER_MINUTE | Giới hạn request theo key, state trong Redis |
| DAILY_BUDGET_USD, MONTHLY_BUDGET_USD | Ngân sách tổng ngày/tháng UTC |
| REDIS_KEY_PREFIX | Namespace state production |

Local/checker mặc định `LLM_PROVIDER=mock`; benchmark Part 7 dùng mock độc lập theo đề. Với Groq, reserve trước mức chi phí tối đa cấu hình rồi quyết toán bằng usage thực. HTTP 4xx upstream bị từ chối được refund; timeout/5xx không chắc usage giữ reservation để không mở lại budget. Lỗi provider trả thông báo chung và log code đã lọc, không lộ key/body upstream.

## Ảnh triển khai

- [dashboard.png](screenshots/dashboard.png): Railway Architecture, agent và Redis đều Online.
- [running.png](screenshots/running.png): agent ACTIVE, public domain và Deployment successful.
- [test.png](screenshots/test.png): báo cáo bốn kết quả HTTPS thực tế, render từ JSON, ghi rõ đây là báo cáo kiểm thử.

Hai ảnh Railway chụp UI thật, chỉ cắt thanh tab/bookmark của browser, không thay nội dung deployment. Ảnh test chụp [public-test.html](reports/cp6/public-test.html), sinh từ JSON bởi [render_cp6_evidence.py](scripts/render_cp6_evidence.py).

## Kiểm thử trước triển khai

Checker nguyên bản đầy đủ có Docker **PASS 12/12, 41/41 checks**: [CP6 checker](reports/cp6/production-readiness.txt). Adapter Groq có [7 test](reports/cp6/groq-adapter-tests.txt); production có [6 test](reports/cp6/production-tests.txt). Groq local test dùng HTTP stub để kiểm accounting/lỗi; request public trên mới là Groq thật. Chi tiết: [reports/cp6/README.md](reports/cp6/README.md).
