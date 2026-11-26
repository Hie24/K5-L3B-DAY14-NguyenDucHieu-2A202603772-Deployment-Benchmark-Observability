# Bằng chứng CP5

Ngày chạy: 2026-11-26 (GMT+7). Ubuntu WSL2, Python host 3.12.3; Docker runtime Python 3.11 slim. Part 6 dùng venv riêng, không thay dependencies CP1–CP4.

## Kết quả

| Kiểm tra | Kết quả | Bằng chứng |
| --- | --- | --- |
| Checker nguyên bản, đầy đủ | PASS 12/12, 41/41 checks, exit 0 | [production-readiness.txt](production-readiness.txt) |
| Image | 286,308,133 byte, 273.045 MiB | [compose.json](compose.json) |
| Docker stop | Exit 0, 1.0 giây | Report checker |
| Test bổ sung | 5/5 đạt, 30.479 giây | [edge-cases.txt](edge-cases.txt), [edge-cases.json](edge-cases.json) |
| Compose thực tế | PORT 50389, health/ready 200, auth 401/200, UID 10001, PID 1 Uvicorn | [compose.txt](compose.txt), [compose.json](compose.json) |

Test bổ sung kiểm input và log, rate limit đồng thời/restart, budget đồng thời, monthly limit, refund, đổi kỳ UTC và Redis down. Counter ngân sách của lượt test cuối là 83,700/100,000 nano-USD cho cả ngày và tháng. Đây là dữ liệu kiểm thử mock, không phải chi phí nhà cung cấp.

## File và cách chạy lại

- [Baseline trước khi triển khai](static-before.txt): 0/12 tiêu chí đạt.
- [Static sau triển khai](static-after.txt): 26/26 checks tĩnh đạt; runtime/Docker chưa được đánh giá trong chế độ này.
- [Log cài dependencies](dependencies.txt), [phiên bản đã cài](dependencies-lock.txt).
- `validation-server.txt`, `rate-server.txt`, `rate-restart-server.txt`, `budget-server.txt`, `monthly-server.txt`, `redis-down-server.txt`: log app JSON và log Uvicorn của các test.

Từ `06-lab-complete/` trong WSL2:

```bash
.venv/bin/python check_production_ready.py
.venv/bin/python tests/test_production.py
```

Từ gốc repo:

```bash
06-lab-complete/.venv/bin/python scripts/verify_cp5_compose.py
```

Các script dùng Redis/project tạm riêng và tự dọn tài nguyên. API key thử nghiệm chỉ tồn tại trong memory/env của tiến trình; không ghi giá trị vào report.

Lần đầu chạy helper kiểm bổ sung có lỗi tra header phân biệt hoa thường và lỗi gọi thuộc tính method trong script ghi log. Đã sửa helper; log ban đầu giữ tại `edge-cases-first-attempt.*`, `compose-first-attempt.txt`. Kết quả cuối là `edge-cases.*`, `compose.*`. Code app và checker không bị thay đổi để xử lý hai lỗi helper đó.

## Phạm vi

Script chấm, golden dataset và mock LLM của đề giữ nguyên. CP5 chuẩn bị cấu hình Railway, chưa có URL public; deployment/Groq thuộc giai đoạn tiếp theo. Câu trả lời và checklist nguyên output nằm trong [MISSION_ANSWERS.md](../../MISSION_ANSWERS.md).
