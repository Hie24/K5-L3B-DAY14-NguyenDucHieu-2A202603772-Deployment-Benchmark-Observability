# CP6 — Railway và Groq

Đã hoàn thành: agent Part 6 và Redis trên Railway, Groq thật, bốn mã HTTP 200/200/401/200 và ba ảnh deploy. Chi tiết và lệnh tái lập: [DEPLOYMENT.md](../../DEPLOYMENT.md).

| File | Nội dung |
| --- | --- |
| [railway-state.json](railway-state.json) | Trạng thái SUCCESS của agent/Redis, deployment IDs và tên biến; không lưu giá trị secret |
| [public-smoke.json](public-smoke.json) | Bốn phép thử HTTPS lúc 2026-11-26 17:33 GMT+7; đúng key gọi Groq với 108 input/30 output tokens |
| [public-smoke-initial.json](public-smoke-initial.json) | Giữ kết quả kiểm lần đầu lúc 16:17 GMT+7 |
| [public-test.html](public-test.html) | Báo cáo được render từ JSON thực, nguồn ảnh test.png; không phải dashboard Railway |
| [deployment-upload.ndjson](deployment-upload.ndjson) | Deployment ID và link log do CLI trả khi upload Part 6 |
| [build-logs.txt](build-logs.txt) | Docker build và image digest trên Railway |
| [runtime-logs.txt](runtime-logs.txt) | Log app và các request kiểm đầu tiên |
| [production-readiness.txt](production-readiness.txt) | Checker đầy đủ nguyên bản: PASS 12/12, 41/41 checks |
| [groq-adapter-tests.txt](groq-adapter-tests.txt) | 7 unit test adapter Groq với HTTP stub |
| [production-tests.txt](production-tests.txt) | 6 integration test, Redis thật, Groq HTTP stub trong test accounting |
| [edge-cases.json](edge-cases.json) | Chi tiết kiểm production; các file *-server.txt là log tương ứng |

Ảnh thật: [dashboard](../../screenshots/dashboard.png), [running](../../screenshots/running.png), [test](../../screenshots/test.png). Hai ảnh Railway chỉ cắt browser chrome; ảnh test là screenshot báo cáo ghi rõ nguồn JSON. Không dùng ảnh tạo bằng AI hoặc mô phỏng trạng thái deployment.

Giữ mock để grader local chạy offline. Test HTTP stub không chứng minh provider thật; chỉ file public-smoke và public-smoke-initial ghi live Groq. Đơn giá cấu hình dùng để estimate/budget, không phải hóa đơn. Không lưu key, token đăng nhập, mật khẩu Redis hoặc file .env vào bằng chứng.
