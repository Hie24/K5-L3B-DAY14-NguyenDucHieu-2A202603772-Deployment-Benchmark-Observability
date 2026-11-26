# Part 6 Production AI Agent

Agent FastAPI cho CP5–CP6, có API key, Redis dùng chung, rate limit, ngân sách ngày/tháng, JSON logging và graceful shutdown. Local mặc định mock; Railway dùng Groq thật. Code giữ nguyên vị trí theo submission K5.

Checker đầy đủ đã đạt **PASS 12/12, 41/41 checks** trên WSL2 có Docker. Output: [checker CP6](../reports/cp6/production-readiness.txt). Public API: https://agent-production-74381197.up.railway.app/docs. Bốn kiểm tra public 200/200/401/200 và ảnh thật ở [DEPLOYMENT.md](../DEPLOYMENT.md).

## Chạy trong WSL2

Từ thư mục này:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Điền key vừa tạo vào `AGENT_API_KEY` trong `.env`, rồi chạy:

```bash
docker compose -p k5-day14-production up -d --build
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

Để test API, đặt biến `AGENT_API_KEY` trong terminal bằng cùng giá trị trong `.env`:

```bash
curl -i -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"What is deployment?","user_id":"demo"}'
```

Nếu đổi `PORT` trong env thì dùng cổng đó trong URL. Không có key hợp lệ thì mọi request `/ask` hợp lệ về body đều bị từ chối. Key của agent khác với key nhà cung cấp LLM.

`docker compose -p k5-day14-production down` dừng stack và giữ volume Redis. Chỉ thêm `--volumes` khi muốn xóa state của stack lab này.

## Script chấm dựa vào những tiêu chí dưới đây

| Hạng mục | Hành vi triển khai |
| --- | --- |
| Entry point | `uvicorn app.main:app --workers 2` từ thư mục này |
| GET /health | Luôn 200 khi process hoạt động, không gọi Redis |
| GET /ready | 200 khi đã có API key, provider được cấu hình và Redis ping được; còn lại 503 |
| POST /ask | JSON question dài 1–2000 ký tự sau khi trim; user_id tùy chọn; input sai 422 |
| Authentication | Header X-API-Key; thiếu/sai hoặc server chưa đặt key đều 401 |
| Rate limit | Sliding window 60 giây theo API key, Lua và sorted set trong Redis; vượt 429 kèm Retry-After |
| Budget | Ngân sách toàn agent theo ngày và tháng UTC; vượt 402 |
| Redis down | Ask trả 503, không chuyển sang state trong RAM |
| Logging | Mỗi dòng app là JSON, có request_id và latency; không log key, Redis URL hay câu hỏi |
| Shutdown | Uvicorn nhận SIGTERM, chờ request rồi lifespan đóng Redis; Docker chạy Uvicorn ở PID 1 |
| Docker | Multi-stage, Python slim, venv riêng, UID 10001, HEALTHCHECK; image <500 MB |
| Compose | Agent và Redis; Redis có healthcheck, AOF, volume; Redis không publish cổng ra host |
| Environment | .env.example đủ biến; .env không nằm trong Git/image; env được inject ưu tiên hơn file .env |
| Railway | Dockerfile builder, healthcheck /health, cổng từ PORT |

## Rate limit và chi phí

Rate limit dùng thời gian Redis để các worker có cùng cửa sổ. Hash SHA-256 của API key được dùng trong tên Redis key, không dùng secret trực tiếp. Kiểm và thêm request nằm trong một Lua script nên các request đồng thời không cùng vượt hạn mức.

Cost guard lưu integer nano-USD, tránh cộng dồn số thực. Trước khi gọi mock, một Lua script kiểm cả ngân sách ngày và tháng rồi giữ trước chi phí tối đa có thể có. Sau khi trả lời, phần giữ trước dư được hoàn lại; mock lỗi trước khi có usage thì hoàn toàn bộ. Nếu process bị SIGKILL giữa chừng, khoản giữ trước vẫn được tính cho kỳ đó để tránh mở lại ngân sách đã cấp.

Key ngân sách chứa ngày/tháng UTC; key cũ giữ thêm một ngày để request đi qua nửa đêm vẫn quyết toán vào kỳ gốc. Budget 0 chặn toàn bộ model call. Các request bị từ chối bởi cost guard vẫn tiêu một lượt rate limit.

Local/checker dùng mock có sẵn, không cần LLM API key. Token ước lượng bằng UTF-8 byte/4 và response ghi `usage.source=mock_estimate`; đơn giá mock chỉ phục vụ lab. Benchmark Part 7 tiếp tục dùng mock độc lập theo đề.

Để bật Groq, đặt `LLM_PROVIDER=groq`, `GROQ_API_KEY` và các biến `GROQ_*` theo `.env.example`; model mặc định `openai/gpt-oss-20b`. Agent gọi HTTPS trực tiếp, timeout tối đa 5 giây, không tự retry provider. Usage thật ghi `groq_reported`; cost estimate lấy đơn giá cấu hình. Budget reserve trước full context + max output, rồi hoàn phần dư theo token usage. Lỗi bị từ chối 4xx được refund; timeout/5xx giữ reservation do không chắc usage. Khi đổi model, phải đặt rõ context window và đơn giá phù hợp. Key của Groq và key client AGENT_API_KEY là hai secret khác nhau.

## Cấu trúc

```text
app/
  main.py            Routes, validation, middleware và lifespan
  config.py          Env, dotenv và validation cấu hình
  auth.py            API key
  redis_client.py    Kết nối lazy, timeout và health
  rate_limiter.py    Sliding window nguyên tử
  cost_guard.py      Reserve, settle và refund ngân sách
  llm.py             Adapter HTTPS Groq, usage validation và lỗi đã lọc
  logging_config.py  JSON formatter
utils/mock_llm.py    Mock của đề, giữ nguyên
tests/test_production.py
Dockerfile
docker-compose.yml
railway.toml
.env.example
check_production_ready.py
benchmark-observability/
```

## Kiểm tra

Với venv của thư mục này đã activate:

```bash
python check_production_ready.py --static-only
python check_production_ready.py
python tests/test_production.py
python -m unittest discover -s tests -p test_groq.py -v
```

Chế độ static-only chỉ xác nhận tĩnh, không thể thay kết quả chấm đầy đủ. Test bổ sung khởi động Redis tạm và agent 2 worker, kiểm input, log, concurrency, restart, budget/refund, đổi kỳ UTC và Redis down. Nó không sửa script chấm hoặc golden dataset.

Từ gốc repo, kiểm Compose trên cổng khác mặc định:

```bash
06-lab-complete/.venv/bin/python scripts/verify_cp5_compose.py
```

Bằng chứng và phiên bản dependencies: [reports/cp5](../reports/cp5/README.md). Câu trả lời và AI log: [MISSION_ANSWERS.md](../MISSION_ANSWERS.md).

## Railway

Đã deploy từ gốc repo bằng `railway up 06-lab-complete --path-as-root --service agent --environment production`: archive root là Part 6, service Root Directory để `/`. Redis trong cùng project, REDIS_URL là reference variable. Secret nhập trên nền tảng; app lắng nghe 0.0.0.0 theo PORT. Chưa cấu hình GitHub autodeploy.

Nếu dùng GitHub source thay cho CLI upload, đặt Root Directory `/06-lab-complete` và config `/06-lab-complete/railway.toml`. [DEPLOYMENT.md](../DEPLOYMENT.md) ghi URL, test, tên biến và ảnh. Render không được chọn; render.yaml chỉ dẫn tới ví dụ tham khảo của đề.
