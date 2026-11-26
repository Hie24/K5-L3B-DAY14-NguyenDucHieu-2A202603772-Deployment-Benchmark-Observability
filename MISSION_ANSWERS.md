# Day 14 Lab Mission Answers

Thực hiện theo các điều chỉnh K5 trong [README.md](README.md), [CHECKPOINTS.md](CHECKPOINTS.md), [SUBMISSION.md](SUBMISSION.md) và [RUBRIC.md](RUBRIC.md).

## CP0 Setup

Ngày kiểm tra: 2026-11-26 (GMT+7).

Trạng thái: **ĐẠT CP0**. Ubuntu WSL2, Python venv và Docker đã chạy được cùng nhau.

| Hạng mục | Trạng thái |
| --- | --- |
| Repository | Đúng tên theo submission; đã clone, nhánh `main` |
| GitHub | Public; fork từ `VinUni-AI20k/K5-L3-Day14-Deployment-Agent-Benchmark-Observability`; owner khớp tài khoản kết nối `Hie24` |
| Git | Windows `2.56.0.windows.1`; Ubuntu `2.43.0` |
| Docker Engine | `29.9.3`, Linux containers; Docker Desktop đã khởi động |
| Docker Compose | `v5.7.0` |
| Docker hello-world | Exit code 0; có thông báo `Hello from Docker!` |
| WSL2 | Ubuntu 24.04.5 LTS, distro `Ubuntu-24.04`, VERSION 2; đã đặt làm mặc định và bật Docker integration |
| Python trong WSL2 | Python `3.12.3`; `os.name` trả `posix` |
| Môi trường ảo | `.venv/` tạo bằng Python Linux; pip `24.0`; đã được Git ignore |
| Hồ sơ bài nộp | Đã tạo khung mission answers, deployment, benchmark report và các thư mục bằng chứng |

Kết quả môi trường: [reports/cp0-setup.txt](reports/cp0-setup.txt). Các phần dưới được bổ sung tại đúng checkpoint bằng output thực tế.

### Mở môi trường làm lab

Từ PowerShell tại thư mục repo, vào Ubuntu (WSL giữ thư mục làm việc hiện tại):

```powershell
wsl -d Ubuntu-24.04
```

Trong terminal Ubuntu tại gốc repo:

```bash
source .venv/bin/activate
python --version
python -c 'import os; print(os.name)'
docker compose version
```

Mong đợi Python 3.12.3, `posix` và Docker Compose v5.7.0. Dependencies dùng cho CP1–CP4 được ghi tại [dependencies-lock.txt](reports/cp1-cp4/dependencies-lock.txt).

## Tiến độ checkpoint

| Checkpoint | Phần của đề | Kết quả |
| --- | --- | --- |
| CP0 | Setup | Đạt; WSL2, venv và Docker hoạt động |
| CP1 | Part 1 | Đạt; chạy develop/production và đối chiếu anti-pattern |
| CP2 | Part 2 | Đạt; build, đo image, test stack qua Nginx |
| CP3 | Part 4 | Đạt; API key, JWT, 429 và kiểm logic cost guard |
| CP4 | Part 5 | Đạt; SIGTERM, 3 instance, Redis history, failover và dependency down |
| CP5 | Part 6 | Đạt; checker đầy đủ PASS 12/12, 41/41 checks; 5/5 test bổ sung và Compose runtime |
| CP6 | Part 3 | Đạt; Railway agent/Redis SUCCESS, public 200/200/401/200 với Groq thật; đủ 3 ảnh và hồ sơ deployment |
| CP7 | Part 7 Bước 1 | Đạt; đủ 7 load test, eval v1/v2, v2 sửa KB 23/23 không regression; negative gate exit 1 |
| CP8 | Part 7 Bước 2 | Đạt; promtool test pass, Locust scale 1 vs 3, 5 thí nghiệm alert A–E, trace+log JSON và 4 ảnh Part 7 |

Bằng chứng CP1–CP4: [mục lục](reports/cp1-cp4/README.md). Các trạng thái này không thay cho kết quả `PASS 12/12` của Part 6.

## Part 1 Localhost vs Production

### Exercise 1.1 Anti-patterns

CP1 đã thực hiện trong Ubuntu WSL2 với Python 3.12.3. Các vấn đề trong `01-localhost-vs-production/develop/app.py`:

| Vị trí | Anti-pattern | Tác động |
| --- | --- | --- |
| Dòng 17–18 | API key và thông tin kết nối database hardcode | Khó đổi giữa môi trường; secret thật sẽ tồn tại trong lịch sử Git nếu commit |
| Dòng 21–22 | Debug và giới hạn token cố định trong code | Muốn đổi cấu hình phải sửa source và triển khai lại |
| Dòng 33–38 | Dùng `print` để log câu hỏi, key và câu trả lời | Lộ dữ liệu nhạy cảm; khó lọc log theo trường |
| Dòng 25–39 | Có `/` và `/ask` nhưng không có `/health`, `/ready` | Platform không có probe chuyên biệt để kiểm tra process và readiness |
| Dòng 51 | Bind `localhost` | Client bên ngoài container không truy cập qua network interface của container được |
| Dòng 52 | Cổng 8000 cố định | Không nhận cổng do nền tảng cloud cấp qua `PORT` |
| Dòng 53 | `reload=True` | Chạy thêm reloader, theo dõi file và có thể restart ngoài dự kiến; phù hợp development |

Đối chiếu cụ thể: host/port cố định ở dòng 51–52 đã được thay bằng `settings.host` và `settings.port` ở bản production; `production/config.py` dòng 17–19 đọc `HOST`, `PORT`, `DEBUG` từ env. Key ở dòng 17 của develop là key giả có sẵn trong đề, không phải key Groq.

### Exercise 1.2 Chạy bản develop

Đã chạy `python app.py` trong `01-localhost-vs-production/develop/`. Trích output thật từ curl (lược bớt header):

```text
POST http://127.0.0.1:8000/ask?question=Hello
HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}

POST /ask với JSON {"question":"Hello"}, không có query
HTTP/1.1 422 Unprocessable Entity
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}

GET /health
HTTP/1.1 404 Not Found
```

App chạy được nhưng còn các vấn đề ở Exercise 1.1. Request dùng query theo README K5, vì tham số `question: str` ở bản develop không phải JSON body.

Lệnh và output đầy đủ: [cp1-transcript.txt](reports/cp1-cp4/cp1-transcript.txt). Log server đã che key demo: [cp1-develop-server.txt](reports/cp1-cp4/cp1-develop-server.txt).

### Exercise 1.3 So sánh develop và production

| Feature | Develop | Production | Vì sao quan trọng |
| --- | --- | --- | --- |
| Config | Host/port/debug cố định | `Settings` đọc env, chạy thử với `ENVIRONMENT=staging`, `DEBUG=false` | Cùng một source dùng được ở nhiều môi trường |
| Secrets | Key/database URL trong source, key còn được in ra log | Đọc key từ env; không log key trong handler | Hạn chế lộ thông tin và hỗ trợ rotation |
| Logging | `print` với nội dung tự do | Có cấu hình formatter và event cho request/response | Mục tiêu là log có cấu trúc để tìm kiếm; cần kiểm tra formatter thực tế |
| Health check | `/health` trả 404 | `/health` trả 200; `/ready` trả 200 khi startup xong | Phân biệt process còn sống với khả năng nhận traffic |
| Shutdown | Uvicorn có xử lý signal mặc định, app chưa có cleanup riêng | Có lifespan startup/shutdown và cập nhật readiness | Có nơi đóng connection/tài nguyên sau khi hoàn tất request |
| Network | `localhost:8000`, reload bật | Host mặc định `0.0.0.0`, port từ env, debug mặc định tắt | Nhận được traffic container/cloud và tránh chạy reloader ở production |

Kết quả production: `/health` 200 với `environment="staging"`; `/ready` 200 với `{"ready":true}`; `POST /ask` JSON trả 200 và câu trả lời về deployment; body thiếu câu hỏi trả 422. Cả hai server đều dừng với exit code 0.

Giới hạn của ví dụ: `config.validate()` log warning trước `logging.basicConfig()` nên trong lần chạy này log thực tế vẫn có dạng `WARNING:root:...`, chưa đạt yêu cầu mỗi dòng app là JSON. Không đánh đồng chú thích "JSON logging" với việc đã kiểm chứng JSON hợp lệ. Bản production còn gọi mock đồng bộ trong handler async; CP1 chỉ so sánh ví dụ, chưa chứng nhận production readiness Part 6.

Bằng chứng: [cp1-summary.json](reports/cp1-cp4/cp1-summary.json), [cp1-production-server.txt](reports/cp1-cp4/cp1-production-server.txt).

## Part 2 Docker

### Exercise 2.1 Dockerfile

1. **Base image:** Dockerfile develop thực tế dùng `FROM python:3.11`, là bản đầy đủ. `python:3.11-slim` là base của Dockerfile production, không phải develop.
2. **Working directory:** `WORKDIR /app`; các bước copy, cài dependencies và chạy app dùng thư mục này làm thư mục hiện tại.
3. **COPY requirements trước source:** lớp cài dependencies được tái sử dụng khi chỉ source thay đổi. Nếu copy tất cả source trước, mỗi lần sửa code sẽ làm mất cache của bước pip phía sau.
4. **CMD và ENTRYPOINT:** `CMD` cung cấp lệnh/tham số mặc định, có thể bị thay bởi phần command của `docker run`. `ENTRYPOINT` xác định executable; với exec form, command của `docker run` thường trở thành tham số cho executable đó. Có thể thay ENTRYPOINT bằng `--entrypoint`. Dockerfile develop dùng `CMD ["python", "app.py"]`.

### Exercise 2.2 Build và chạy container

Build từ gốc repo theo README K5:

```bash
docker build --progress=plain -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name k5-day14-cp2-basic -p 127.0.0.1:8000:8000 my-agent:develop
```

Container chạy được: `GET /health` 200; `POST /ask?question=What%20is%20Docker%3F` 200:

```json
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

Đã lưu `docker logs`, sau đó xóa đúng container vừa tạo để trả cổng 8000. Bằng chứng: [build develop](reports/cp1-cp4/cp2-build-develop.txt), [cp2-transcript.txt](reports/cp1-cp4/cp2-transcript.txt).

### Exercise 2.3 So sánh image

Production build cũng chạy từ gốc repo:

```bash
docker build --progress=plain -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent
docker image inspect my-agent:develop my-agent:advanced
```

| Image | `docker images` DISK USAGE | CONTENT SIZE | `.Size` từ inspect (byte) | MB theo `.Size` |
| --- | ---: | ---: | ---: | ---: |
| `my-agent:develop` | 1.67 GB | 426 MB | 1,667,784,298 | 1667.784 |
| `my-agent:advanced` | 240 MB | 57.4 MB | 239,819,526 | 239.820 |

MB ở bảng dùng 1 MB = 1,000,000 byte. Tính trên cùng trường `.Size`: `(1,667,784,298 - 239,819,526) / 1,667,784,298 * 100 = 85.62%` giảm. Cột content size là số Docker hiển thị riêng; không trộn với disk usage để tính phần trăm.

Stage builder dùng slim, cài `gcc`, `libpq-dev` và Python dependencies vào `/root/.local`. Stage runtime bắt đầu lại từ slim, chỉ copy dependencies đã cài và source cần chạy; compiler và các lớp apt của builder không nằm trong runtime. Việc đổi full sang slim cũng góp phần lớn vào chênh lệch, nên không quy toàn bộ 85.62% cho multi-stage.

Runtime dùng user `appuser`, có HEALTHCHECK và Uvicorn 2 worker. `docker compose exec -T agent id` xác nhận UID 999 không phải root. HEALTHCHECK đánh dấu healthy/unhealthy; riêng nó không tự restart container. Restart policy xử lý trường hợp process/container thoát.

Bằng chứng: [docker images](reports/cp1-cp4/cp2-images.txt), [inspect](reports/cp1-cp4/cp2-image-inspect.json), [build production](reports/cp1-cp4/cp2-build-production.txt), [summary](reports/cp1-cp4/cp2-summary.json).

### Exercise 2.4 Compose stack

Đã tạo `.env.local` rỗng, được Git ignore, và chạy trong `02-docker/production/`:

```bash
docker compose -p k5-day14-docker up -d --build --wait --wait-timeout 180
```

```text
Client localhost:80
        |
    nginx:80  ---- HTTP ----> agent:8000 (Uvicorn 2 worker)
                                  |
                        cấu hình và depends_on
                            /             \
                     redis:6379       qdrant:6333
                     /data volume     storage volume
```

Bốn service là agent, Redis, Qdrant và Nginx; cùng network `internal` của project. Redis/Qdrant có healthcheck và persistent volume; agent đợi hai service healthy. Compose này thực tế khởi động **1 container agent**, không phải 2 replica như phần comment. Agent được cấu hình URL Redis/Qdrant, nhưng `main.py` hiện chỉ gọi mock, chưa sử dụng hai backend trong logic `/ask`.

Test qua `http://127.0.0.1` trên Nginx: `/health` 200, `/ready` 200, `POST /ask` JSON 200; response có `Server: nginx` và security headers. `redis-cli ping` trả `PONG`. Port 443 có mapping nhưng cấu hình Nginx hiện chỉ listen HTTP 80, chưa có HTTPS/certificate.

Đã lưu `compose ps`, log các service và dọn project bằng `docker compose -p k5-day14-docker down --volumes`. Kết quả trong [cp2-transcript.txt](reports/cp1-cp4/cp2-transcript.txt).

## Part 3 Cloud Deployment

### Exercise 3.1 Railway

Nền tảng đã chọn: Railway, project `k5-day14-agent`, environment `production`. Agent Part 6 tại `06-lab-complete/` đã build Dockerfile và deploy bằng CLI, cùng service Redis nội bộ. Public URL: **https://agent-production-74381197.up.railway.app**. Kiểm lại ngày 2026-11-26 lúc 17:33 GMT+7: `/health` 200, `/ready` 200, `/ask` thiếu key 401, đúng key 200; provider Groq, model `openai/gpt-oss-20b`, usage provider báo 108 input / 30 output tokens.

Đã đặt AGENT_API_KEY, GROQ_API_KEY và REDIS_URL trên Railway; không hardcode secret. Lệnh deploy dùng `--path-as-root`, nên archive có Dockerfile/railway.toml tại root. Bản chạy là CLI upload; chưa cấu hình GitHub autodeploy. [DEPLOYMENT.md](DEPLOYMENT.md) ghi đầy đủ env names, bốn lệnh test và bằng chứng. Ảnh: [dashboard](screenshots/dashboard.png), [running](screenshots/running.png), [test](screenshots/test.png).

### Exercise 3.2 So sánh Railway và Render

Đối chiếu file đã dùng [06-lab-complete/railway.toml](06-lab-complete/railway.toml) với ví dụ [03-cloud-deployment/render/render.yaml](03-cloud-deployment/render/render.yaml). File `06-lab-complete/render.yaml` chỉ là chỉ dẫn tham khảo, không phải Blueprint hoàn chỉnh; không tuyên bố đã deploy Render.

| Nội dung | Railway TOML của bài làm | Render YAML mẫu | Giải thích |
| --- | --- | --- | --- |
| Phạm vi | Build/deploy cho một service agent; Redis tạo riêng trong project | Blueprint có mảng services gồm web và Redis | Render mẫu mô tả nhiều tài nguyên trong cùng file; Railway file hiện tại không tự tạo Redis |
| Build/runtime | DOCKERFILE, đường dẫn Dockerfile; CMD trong image chạy app.main:app | runtime python, buildCommand pip install, startCommand uvicorn app:app | Railway dùng cùng image như local; mẫu Render chạy Python native và app mẫu có entry point khác Part 6 |
| Health/restart | /health, timeout 60s, ON_FAILURE tối đa 3 lần | healthCheckPath /health, autoDeploy true | Cùng probe HTTP; hai file hiện tại khai báo các tùy chọn deploy khác nhau |
| Env/secret | Secret và reference Redis được đặt qua Variables; không nằm trong TOML | envVars có value, sync:false và generateValue:true | Cả hai cần secret ngoài source; Render mẫu yêu cầu nhập OPENAI_API_KEY và tự sinh AGENT_API_KEY |
| Region/plan/Redis | Chọn trong project/service; Redis là service riêng có volume | region singapore, plan free, type redis và eviction policy trong YAML | Đây là khác biệt cấu hình trong hai file, không đảm bảo gói/giá nền tảng luôn giữ nguyên |

Nếu chuyển Part 6 sang Render, cần viết Blueprint đúng entry point `app.main:app` hoặc chọn Docker runtime, thêm REDIS_URL reference và Groq env, rồi kiểm đủ bốn API; không dùng nguyên startCommand `app:app` của ví dụ cho Part 6. Bài K5 cho phép so sánh cấu hình để đáp ứng phần nền tảng còn lại, nên không cần deploy thêm.

### Exercise 3.3 Pipeline Cloud Run

1. [cloudbuild.yaml](03-cloud-deployment/production-cloud-run/cloudbuild.yaml) chạy bước test bằng Python 3.11, cài requirements/pytest và gọi `pytest tests/`; build chờ bước test qua `waitFor`.
2. Docker build image gắn tag COMMIT_SHA và latest, dùng image latest làm cache; bước push đẩy các tag lên `gcr.io/$PROJECT_ID/ai-agent` trước khi deploy.
3. Bước deploy gọi `gcloud run deploy` image theo COMMIT_SHA ở asia-southeast1, public endpoint, 1–10 instance, 1 CPU/512Mi, timeout 60s; env production và secret từ Secret Manager.
4. [service.yaml](03-cloud-deployment/production-cloud-run/service.yaml) mô tả service container cổng 8000, concurrency 80, min/max scale 1/10, liveness/startup probe và secret references; pipeline mẫu deploy bằng CLI flags, không tự apply file service.yaml.
5. Cần thêm `set -e` trong shell test trước khi dùng CI thật: file mẫu có `echo` sau pytest nên có thể che exit code lỗi; bài này chỉ đọc/giải thích cấu hình, không triển khai GCP.

## Part 4 API Security

### Exercise 4.1 API key

CP3 chạy ví dụ có sẵn theo hướng dẫn K5. Key demo được tạo ngẫu nhiên trong memory và truyền qua `AGENT_API_KEY`; key và JWT được che trong mọi file bằng chứng.

`verify_api_key()` trong `04-api-gateway/develop/app.py` kiểm header `X-API-Key`, được nối vào `/ask` bằng `Depends`. Thiếu key trả 401; sai key trả 403 ở **ví dụ Part 4 này**. Part 6 có hợp đồng riêng yêu cầu cả thiếu và sai đều 401.

Trích output thật của `curl -i` (lược bớt header):

```text
POST /ask không có X-API-Key
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

POST /ask với key sai
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

POST /ask với X-API-Key: <REDACTED>
HTTP/1.1 200 OK
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

Rotation: thay secret ở biến môi trường, cập nhật client và restart/redeploy toàn bộ worker vì ví dụ đọc key lúc import. Không sửa key thật vào source. Bản develop còn in key khi startup, vì vậy log lưu của lần chạy này đã được che trước khi ghi xuống disk.

### Exercise 4.2 JWT

Đã lấy token bằng `POST /auth/token` với tài khoản demo `student` theo README K5. `authenticate_user()` kiểm credentials, `create_token()` ký HS256 với secret truyền qua `JWT_SECRET`; payload có `sub`, `role`, `iat`, `exp`, thời hạn 60 phút. Client gửi `Authorization: Bearer <token>`, dependency verify kiểm chữ ký và expiry trước khi vào handler.

```text
POST /auth/token
HTTP/1.1 200 OK
{"access_token":"<REDACTED>","token_type":"bearer","expires_in_minutes":60,"hint":"<REDACTED>"}

POST /ask với Bearer <REDACTED>
HTTP/1.1 200 OK
```

Kiểm chứng role: student gọi `/admin/stats` nhận 403; teacher nhận 200. Token là chứng nhận quyền do server ký, không phải dữ liệu được mã hóa; không đưa secret vào payload. Đăng nhập/role demo chỉ dùng trong lab.

### Exercise 4.3 Rate limiting

Algorithm thực tế là **sliding window log**: mỗi user có deque timestamps; bỏ timestamp quá 60 giây rồi đếm số còn lại. Source gọi nó là counter, nhưng lưu từng timestamp chứ không dùng token bucket.

- User: 10 request/60 giây.
- Admin: 100 request/60 giây, **không bypass vô hạn**; handler chọn limiter theo role đã xác thực từ JWT.
- State hiện ở RAM từng process; restart hoặc chạy nhiều worker sẽ làm giới hạn không còn được chia sẻ. Redis được triển khai ở Part 6.

Đã gửi 20 request liên tiếp với cùng JWT student: **10 lần 200, 10 lần 429**. Request thứ 11 bị chặn; response cuối có:

```text
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 58

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":58}}
```

Sau chuỗi request, `/me/usage` trả 200, ghi nhận 10 request, 40 input token, 312 output token, chi phí mock 0.000193 USD. Đây là token ước lượng của ví dụ, không phải usage Groq hay tiền đã thanh toán.

Lệnh curl, output đầy đủ và header đã che token: [cp3-transcript.txt](reports/cp1-cp4/cp3-transcript.txt). Dữ liệu tổng hợp: [cp3-summary.json](reports/cp1-cp4/cp3-summary.json).

### Exercise 4.4 Cost guard

Theo CP3 K5, phần này đọc/chạy ví dụ và giải thích; không viết lại module mẫu. Flow trong `production/app.py`: xác thực JWT → rate limit → `check_budget(username)` → gọi mock → `record_usage(input_tokens, output_tokens)`.

Chi phí theo constants của ví dụ: `input_tokens / 1000 * 0.00015 + output_tokens / 1000 * 0.0006`. Ví dụ giới hạn mỗi user 1 USD/ngày, toàn hệ thống 10 USD/ngày; vượt user budget trả 402, vượt global budget trả 503. Record mỗi user thay mới khi ngày đổi. `_global_cost` trong code mẫu chưa có logic reset ngày dù có biến `_global_today`.

Đã kiểm module `CostGuard` trực tiếp bằng dữ liệu token tổng hợp có ghi rõ trong transcript: budget 0.000001 USD, cộng 1,000 input + 1,000 output token tạo chi phí 0.00075 USD; lần `check_budget` tiếp theo raise HTTP 402. Đây là kiểm logic bằng dữ liệu tổng hợp, không phải load test hay gọi nhà cung cấp.

Với yêu cầu thiết kế 10 USD/tháng trong Exercise 4.4, state nên đặt trong Redis bằng key chứa user và tháng UTC, ví dụ `budget:<user>:YYYY-MM`, kèm TTL sau cuối kỳ. Trước khi gọi LLM, kiểm `spent + reserved + estimated_cost <= budget` và reserve bằng thao tác nguyên tử (Lua/transaction); sau call cập nhật chi phí thực tế và hoàn phần reserve dư. Cách này chia sẻ state giữa worker và tránh nhiều request đồng thời cùng vượt budget. Đơn giá, giới hạn và thời điểm reset phải được cấu hình rõ.

Rate limit bảo vệ tốc độ/tài nguyên, cost guard bảo vệ tổng ngân sách; request ít nhưng prompt dài vẫn có thể tốn tiền. Vì vậy cần cả hai. Trường `usage.budget_remaining_usd` trong response `/ask` mẫu đang gán nhầm chi phí đã dùng; số remaining được đối chiếu từ `/me/usage`, nơi tính `budget - cost` đúng.

## Part 5 Scaling and Reliability

### Exercise 5.1 Health và readiness

CP4 đã chạy bản develop và stack production. Bản develop trả `/health` 200 với `status="ok"`, có thông tin uptime, môi trường và memory; `/ready` 200 với `ready=true` sau startup.

Liveness trả lời process còn hoạt động không; readiness trả lời instance có đủ điều kiện nhận request nghiệp vụ không. Redis lỗi không có nghĩa process đã chết. Khi dừng Redis trong stack đang hoạt động, kiểm trực tiếp cả hai agent còn sống và qua Nginx đều thu được:

```text
GET /health
HTTP/1.1 200 OK
status: degraded
storage: redis
redis_connected: false

GET /ready
HTTP/1.1 503 Service Unavailable
{"detail":"Redis not available"}
```

Health 200 cho phép giám sát process; readiness 503 báo phụ thuộc chưa sẵn sàng. Trong mẫu, nếu Redis không kết nối ngay lúc import thì app chuyển sang fallback RAM; nhánh đó không đáp ứng stateless. Kết quả ở đây được kiểm với `storage="redis"`, sau đó chủ động làm Redis mất kết nối.

### Exercise 5.2 Graceful shutdown

Đã chạy `05-scaling-reliability/develop/app.py`, gửi `POST /ask?question=Long%20task` bằng curl trong thread riêng, chờ 50 ms rồi gửi SIGTERM tới đúng process đã khởi động.

Kết quả lần chạy cuối:

```text
Graceful shutdown: in-flight HTTP 200, exit 0, 3.222s
```

Log server xác nhận `Shutting down`, request `/ask` trả 200, rồi mới `Application shutdown complete`. Uvicorn xử lý signal và chờ request; lifespan hạ readiness và dọn tài nguyên. Không dùng SIGKILL vì signal đó không cho app cơ hội cleanup. Đây là kiểm với độ trễ mock có sẵn, không phải kiểm mọi request dài tới 30 giây.

Log: [cp4-health-server.txt](reports/cp1-cp4/cp4-health-server.txt).

### Exercise 5.3 Stateless design

Mỗi process/container có RAM riêng: session ghi ở instance A không tự xuất hiện ở instance B, và mất khi A restart. Stateless ở đây nghĩa là các instance không giữ business state riêng cần thiết để xử lý request kế tiếp; client gửi `session_id`, instance nào cũng có thể đọc state chung.

Trong `production/app.py`, `save_session()` dùng Redis `SETEX session:<id>` với TTL mặc định 3,600 giây; `load_session()` đọc và parse JSON. History giữ tối đa 20 message. Vì cùng dùng một Redis nên ba instance có cùng history, kể cả khi instance vừa phục vụ bị dừng.

Mẫu còn nhánh fallback RAM và thao tác history read-modify-write chưa nguyên tử. Kết quả test tuần tự chứng minh chia sẻ/persist state ở nhánh Redis; chưa chứng minh không mất update nếu cùng session nhận nhiều request đồng thời. Mock chỉ nhận câu hỏi hiện tại, nên bài này kiểm lưu history, không đánh giá khả năng LLM nhớ context.

### Exercise 5.4 Load balancing

Đã tạo `.env.local` rỗng trong `05-scaling-reliability/production/`, rồi chạy:

```bash
docker compose -p k5-day14-scaling up -d --build --wait --wait-timeout 180 --scale agent=3
```

```text
Client localhost:8080 -> Nginx:80 -> agent x3:8000 -> Redis:6379
```

Agent không publish port trực tiếp; Nginx giải tên service `agent` để có danh sách backend và phân phối request. `X-Served-By` chứa upstream IP, response JSON chứa `served_by` để đối chiếu instance. Đã thấy cả ba instance phục vụ:

```text
Request 1: instance-e2e8b5
Request 2: instance-f78e91
Request 3: instance-115be4
Request 4: instance-e2e8b5
Request 5: instance-f78e91
```

Kiểm tra bổ sung dùng session riêng: request đầu được `instance-f78e91` phục vụ; runner đối chiếu `X-Served-By` với `docker inspect` rồi dừng đúng container đó. Request tiếp theo vẫn 200 qua `instance-115be4`; history chứa đủ 4 message của 2 lượt hỏi–đáp. Đây là bước failover bổ sung của runner, không phải hành vi tự có trong `test_stateless.py`.

Các lỗi phát hiện và sửa trong khi thực hiện CP4:

| File | Vấn đề thực tế | Sửa và kiểm chứng |
| --- | --- | --- |
| `05-scaling-reliability/production/app.py` | Redis client chưa giới hạn socket timeout/retry | Đặt connect/read timeout 1 giây và retry 0; probe trực tiếp trên từng agent trả đúng 200/503 khi Redis dừng |
| `05-scaling-reliability/production/nginx.conf` | Timeout mặc định làm request chờ backend đã dừng quá lâu | Đặt connect timeout 2 giây, read timeout 10 giây cho mọi location; health qua Nginx trả 200 sau khi thử backend khác |
| Cùng file Nginx | Retry HTTP 503 của readiness sang backend đã dừng có thể đổi kết quả thành 502 HTML | Thêm location riêng `/ready`, chỉ retry lỗi kết nối/timeout; giữ readiness 503 của ứng dụng |

Trong lần chạy cuối, header health `X-Served-By: 172.20.0.4:8000, 172.20.0.5:8000` cho thấy request đã thử backend thứ hai. Các log lỗi trước được giữ nguyên tại [lần đầu](reports/cp1-cp4/cp4-initial-attempt-transcript.txt), [lần hai](reports/cp1-cp4/cp4-second-attempt-transcript.txt), [lần ba](reports/cp1-cp4/cp4-third-attempt-transcript.txt); kết quả cuối ở [cp4-transcript.txt](reports/cp1-cp4/cp4-transcript.txt).

Cấu hình retry Redis được đối chiếu với [tài liệu redis-py](https://redis.readthedocs.io/en/stable/retry.html). Nginx mẫu vẫn giải danh sách backend lúc startup; bài test dừng một instance, không chứng minh tự phát hiện IP mới khi recreate container.

### Exercise 5.5 Kiểm tra stateless

Đã chạy nguyên script đề bài bằng Python venv trong thư mục production. Trích output thật:

```text
Stateless Scaling Demo
Session ID: 04c59eb2-2196-4c40-82cf-c38053cd4aa7
Total requests: 5
Instances used: {'instance-e2e8b5', 'instance-115be4', 'instance-f78e91'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Mỗi request thêm một message user và một message assistant; 5 request tạo 10 message. Cả ba instance được sử dụng nhưng history vẫn đủ vì Redis dùng chung. Script có sẵn không tắt instance; runner đã thêm kịch bản dừng instance như Exercise 5.4 và kiểm lại history độc lập.

Đã lưu `compose ps`, log, kết quả kiểm Redis down và dọn stack bằng `docker compose -p k5-day14-scaling down --volumes`. Script đề bài không bị sửa.

Bằng chứng: [test_stateless.py output](reports/cp1-cp4/cp4-test-stateless.txt), [summary](reports/cp1-cp4/cp4-summary.json), [transcript đầy đủ](reports/cp1-cp4/cp4-transcript.txt). Có thể chạy lại bằng `.venv/bin/python scripts/run_cp1_cp4.py cp4` từ gốc repo trong WSL2.

## Part 6 Production Readiness

CP5 đã hoàn thành trong `06-lab-complete/`, chạy Python trên Ubuntu WSL2 và Docker Linux. Script chấm, golden dataset và mock LLM của đề giữ nguyên.

### Triển khai

| Thành phần | Cách thực hiện |
| --- | --- |
| Config | Env và dotenv với env được inject ưu tiên; kiểm port, rate, budget, timeout và log level |
| API key | Header `X-API-Key`, so sánh constant-time; thiếu/sai/không cấu hình đều 401 |
| Health và readiness | Health không phụ thuộc Redis; ready cần key đã đặt và Redis ping thành công; không fallback RAM |
| Rate limit | Sliding window 60 giây theo hash API key, Redis TIME, sorted set và Lua nguyên tử; 429 có Retry-After |
| Cost guard | Ngân sách toàn agent theo ngày và tháng UTC; reserve trước model call, settle/refund sau call; integer nano-USD trong Redis |
| Logging | JSON formatter; middleware ghi request_id, route, status, latency; không ghi key hoặc câu hỏi |
| Error handling | Input sai 422; budget 402; Redis không dùng được 503; lỗi nội bộ 500 với thông báo chung |
| Shutdown | Giữ signal handler của Uvicorn; lifespan đóng client Redis sau khi drain request |
| Docker | Multi-stage Python slim, venv ở /opt/venv, UID 10001, HEALTHCHECK theo PORT, Uvicorn PID 1 |
| Compose | Agent và Redis có healthcheck; AOF và volume Redis; .env tùy chọn; Redis dùng mạng nội bộ |
| Railway | Builder Dockerfile, healthcheck /health, nhận PORT; đã deploy CP6, xem DEPLOYMENT.md |

Input question được trim và giới hạn 1–2000 ký tự; `user_id` tùy chọn không thay API key hay quota. Request bị chặn budget vẫn tiêu một lượt rate limit. Ngân sách là tổng của agent, không phải mỗi `user_id`.

Cost guard giữ trước chi phí tối đa từ tập response mock có sẵn, kiểm cả hai kỳ trong cùng một Lua script, rồi hoàn phần dư. Nếu mock lỗi trước khi sinh usage thì hoàn toàn bộ. Nếu process bị SIGKILL trước quyết toán, phần reserve vẫn được tính để không mở lại ngân sách đã cấp. Key ngày/tháng khác nhau theo UTC nên kỳ mới không dùng counter của kỳ cũ.

CP5 dùng mock; token và chi phí là ước lượng được đánh dấu `mock_estimate`, không phải usage Groq hay tiền thanh toán. Tích hợp Groq và URL Railway còn thuộc giai đoạn sau. Tiêu chí "Public URL ready" trong checker ở CP5 kiểm cấu hình, không chứng minh đã deploy.

### Kết quả checker đầy đủ

Lệnh đã chạy trong `06-lab-complete/`, bằng venv riêng của thư mục này:

```bash
.venv/bin/python check_production_ready.py
```

Output checklist dưới đây được chép nguyên từ file report:

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 41/41 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Checker đo image khoảng 273 MiB và `docker stop` thoát mã 0 trong 1.0 giây. Kiểm Compose riêng ghi chính xác **286,308,133 byte = 273.045 MiB**. Key ngẫu nhiên và giới hạn 5/phút từ env được checker nhận đúng; restart agent vẫn trả 429; budget gần 0 bị chặn 402 ngay request đầu.

### Kiểm tra bổ sung

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| Auth và input | Thiếu/sai/rỗng key đều 401; 7 kiểu input lỗi đều 422; body hợp lệ có user_id trả 200 |
| Concurrent rate limit | 24 request, 2 worker: 5 lần 200, 19 lần 429; Retry-After hợp lệ |
| Restart và cửa sổ cũ | Restart vẫn 429; thay timestamp bằng dữ liệu ngoài cửa sổ 61 giây thì request kế tiếp 200 |
| Concurrent budget | 24 request: 5 lần 200, 19 lần 402; counter ngày/tháng đều 83,700 nano-USD, dưới giới hạn 100,000 |
| Ngân sách tháng | Daily còn tiền nhưng monthly bằng 0 vẫn trả 402 |
| Redis down | Health 200, ready 503, ask có key 503; không lộ lỗi kết nối ra response |
| Log | 18 record JSON trong test validation; không chứa API key hoặc nội dung câu hỏi kiểm tra |
| Refund và đổi kỳ | Inject lỗi mock hoàn counter ngày/tháng về 0; test key ở ranh giới ngày/tháng/năm UTC |
| Compose runtime | Cổng 50389: health/ready 200, thiếu key 401, có key 200; UID 10001; Uvicorn PID 1; Redis PONG |

`tests/test_production.py` có 5 test chạy đạt, dùng Redis tạm và namespace riêng. Dữ liệu timestamp cũ/lỗi mock/ranh giới năm là dữ liệu kiểm thử chủ động, không phải số đo benchmark. Script kiểm Compose đã dọn container/volume của project riêng; checker và tests cũng dọn Redis tạm.

Bằng chứng: [checker đầy đủ](reports/cp5/production-readiness.txt), [5 test](reports/cp5/edge-cases.txt), [JSON kết quả](reports/cp5/edge-cases.json), [Compose log](reports/cp5/compose.txt), [Compose JSON](reports/cp5/compose.json), [mục lục CP5](reports/cp5/README.md).

## Part 7 Bước 1 — CP7

Đã chạy agent mock độc lập trong `06-lab-complete/benchmark-observability/develop/` bằng venv riêng trên WSL2. Bốn mức concurrency 1/10/50/100 và ba slow rate 0/0.03/0.1 đều có 300 request và file JSON. Giữ nguyên kết quả FAIL SLO ở concurrency 100 và slow rate 0.1.

Eval v1 đạt 1/23, v2 ban đầu đạt 21/23. Hai câu `security-02` và `scaling-03` thiếu kiến thức JWT/HPA; đã thêm hai entry trong KNOWLEDGE_BASE, restart v2 và chạy `--min-accuracy 1.0 --baseline reports/eval_v2.json`: **23/23, 0 regression, quality gate PASS, exit 0**. Dataset và các script chấm không bị sửa. Chạy v1 với baseline v2 cũng đã chứng minh gate chặn 20 regression bằng exit 1.

Số đo, phân tích p95/p99, cost/câu đúng và cách dùng exit code chặn merge nằm trong [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md), mục 1–3. JSON được lưu cả trong develop/reports và [reports/](reports/); log, cấu hình, hash và lệnh tại [reports/cp7/README.md](reports/cp7/README.md). Tất cả process CP7 đã được dừng.

## Part 7 Bước 2 — CP8

Đã chạy full observability stack trong `06-lab-complete/benchmark-observability/production/` bằng Docker Compose (`-p k5-day14-observability`), sửa `PYTHONUSERBASE=/home/agent/.local` trong `production/Dockerfile` để container non-root `agent` tìm đúng package, chạy unit test `promtool` cho `alert_rules_test.yml` (`SUCCESS`), benchmark Locust headless `scale_1` và `scale_3` (100 users, 2 phút, `--no-deps`), thực hiện đủ 5 thí nghiệm fault injection (A–E), đối chiếu `trace_id` giữa Jaeger và JSON log, chụp đủ 4 ảnh Part 7 vào `screenshots/` và dọn stack bằng `docker compose down -v`. Chi tiết số liệu và phân tích được ghi trong [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md), mục 4–6; CSV lưu tại [benchmark-results/](benchmark-results/).

## AI log

| Ngày | Yêu cầu với AI | Hỗ trợ đã nhận | Tự sửa và tự kiểm tra của học viên |
| --- | --- | --- | --- |
| 2026-11-26 | Clone và đọc hiểu repository | Codex clone repo, đọc tài liệu và giải thích cấu trúc, TODO Part 6 | Chưa ghi nhận xác nhận tự kiểm; học viên bổ sung sau khi đọc lại |
| 2026-11-26 | Lập kế hoạch theo đề, chọn Railway và Groq | Codex đối chiếu checkpoint, submission, rubric; đề xuất mock cho chấm/benchmark và Groq cho app cloud | Chưa ghi nhận thay đổi/tự kiểm của học viên |
| 2026-11-26 | Thực hiện CP0 | Codex kiểm tra GitHub, công cụ, Docker hello-world, chuẩn bị WSL2 và khung hồ sơ; kết quả cuối ở `reports/cp0-setup.txt` | Học viên cần đọc kết quả, chạy lại các lệnh CP0 và bổ sung kết quả tự kiểm |
| 2026-11-26 | Thực hiện CP1–CP4 | Codex đọc/chạy ví dụ Part 1, 2, 4, 5 trong WSL2; build và đo image; lưu curl/output đã che key và JWT; viết runner tái lập; sửa timeout Redis/Nginx và cách chuyển tiếp readiness; cập nhật giải thích từ code và kết quả thật | Chưa ghi nhận thao tác tự sửa/tự kiểm của học viên; học viên cần chạy lại runner, đối chiếu log và giải thích các thay đổi CP4; không xem kết quả chạy bởi AI là xác nhận đã tự kiểm |
| 2026-11-26 | Thực hiện CP5 | Codex triển khai Part 6 gồm auth, rate limit Redis, budget reserve/settle/refund, config, JSON log, lifespan, Docker/Compose/Railway; tạo và chạy test bổ sung; checker nguyên bản PASS 12/12, 41/41 checks; 5 test và Compose runtime đều đạt; cập nhật README và bằng chứng | Chưa ghi nhận thao tác tự sửa/tự kiểm của học viên; cần chạy lại các lệnh, đọc Lua rate/budget, giải thích health/ready, PID 1, SIGTERM và đối chiếu output trước khi xác nhận đã tự kiểm |
| 2026-11-26 | Thực hiện CP6 trên Railway với Groq | Codex thêm adapter Groq, chạy 7 test adapter và 6 test production, checker 41/41; tạo project agent/Redis, deploy và kiểm public 200/200/401/200 với usage Groq thật. Công cụ browser dừng trước bước chụp ảnh nên hồ sơ CP6 còn thiếu | Học viên đã xác nhận đăng nhập Railway và đặt key trên nền tảng; chưa có xác nhận tự kiểm code/API |
| 2026-11-26 | Thực hiện CP7 | Codex đọc yêu cầu, tạo venv riêng và runner, chạy 7 load test và 4 eval, thêm KB JWT/HPA, đạt 23/23 không regression; giữ kết quả SLO FAIL, ghi lỗi kiểm cổng và chạy tiếp tail; điền báo cáo từ JSON, giải thích CI exit code và dọn process | Chưa ghi nhận thao tác tự sửa/tự kiểm của học viên; cần đối chiếu JSON, chạy lại eval ở output riêng, giải thích p95/p99, cost/câu đúng và 20 regression trước khi xác nhận đã tự kiểm |
| 2026-11-26 | Hoàn thiện phần còn thiếu trước khi học viên tự nộp | Codex kiểm lại Railway SUCCESS và bốn API public với Groq thật; hoàn thiện DEPLOYMENT, so sánh cấu hình Railway/Render, đọc pipeline Cloud Run; chụp UI Railway Online/ACTIVE và ảnh báo cáo HTTPS từ JSON; đối chiếu file, quét secret và chuẩn bị commit/push repo | Học viên tự nộp link LMS; chưa có xác nhận tự kiểm kỹ thuật, cần đọc lại hồ sơ và giải thích số liệu/code khi Lab Coach hỏi |
| 2026-11-26 | Thực hiện CP8 | Antigravity sửa `PYTHONUSERBASE` trong `production/Dockerfile`, chạy `promtool` test rules, chạy Locust headless `scale_1` và `scale_3` (`--no-deps`), chạy 5 thí nghiệm A–E đo thời gian firing, trích xuất `trace_id` và JSON log, chụp 4 ảnh Part 7 (`grafana-dashboard.png`, `jaeger-slow-trace.png`, `jaeger-error-trace.png`, `prometheus-alert-firing.png`), điền `BENCHMARK_REPORT.md` và dọn stack | Học viên cần kiểm tra lại 4 ảnh trong `screenshots/`, đối chiếu số trong `BENCHMARK_REPORT.md` với `benchmark-results/scale_*.csv` và hoàn thiện phần CP6 (ảnh + `DEPLOYMENT.md` nếu cần) trước khi push nộp |
