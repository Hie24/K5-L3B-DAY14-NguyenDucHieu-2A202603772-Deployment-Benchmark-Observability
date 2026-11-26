# Bằng chứng CP1 đến CP4

Ngày chạy: 2026-11-26 (GMT+7). Môi trường: Ubuntu 24.04 WSL2, Python venv 3.12.3, Docker Linux 29.9.3, Compose v5.7.0. Các ví dụ dùng mock LLM.

| Checkpoint | Kết quả | Dữ liệu tổng hợp | Lệnh và output |
| --- | --- | --- | --- |
| CP1 Part 1 | Develop query 200, JSON sai kiểu 422; production health/ready/ask 200 | [summary](cp1-summary.json) | [transcript](cp1-transcript.txt) |
| CP2 Part 2 | Build hai image, giảm dung lượng 85.62%; Nginx API 200 | [summary](cp2-summary.json) | [transcript](cp2-transcript.txt) |
| CP3 Part 4 | API key 401/403/200; JWT; burst 10 lần 200 rồi 10 lần 429; cost guard module 402 | [summary](cp3-summary.json) | [transcript](cp3-transcript.txt) |
| CP4 Part 5 | SIGTERM giữ request 200, exit 0; 3 instance và history; failover; Redis down 200/503 | [summary](cp4-summary.json) | [transcript](cp4-transcript.txt) |

Giải thích và câu trả lời nằm trong [MISSION_ANSWERS.md](../../MISSION_ANSWERS.md). Đây là bằng chứng CP1–CP4, không phải benchmark Part 7 hay kết quả chấm Part 6.

## Dependencies và build

- [Log cài dependencies](dependencies.txt), [phiên bản đã cài](dependencies-lock.txt).
- [Build develop](cp2-build-develop.txt), [build production](cp2-build-production.txt).
- [docker images](cp2-images.txt), [image inspect](cp2-image-inspect.json).
- [Build CP4 lần đầu](cp4-build-progress.txt).
- Log server local: `cp1-*-server.txt`, `cp3-*-server.txt`, `cp4-health-server.txt`.
- [Output nguyên script stateless của đề](cp4-test-stateless.txt).

## Lỗi và lần chạy cuối

Các lần kiểm CP4 trước gặp timeout qua Nginx hoặc readiness bị đổi thành 502. Giữ log tại `cp4-initial-attempt-transcript.txt`, `cp4-second-attempt-transcript.txt`, `cp4-third-attempt-transcript.txt`. File `cp4-transcript.txt` và `cp4-summary.json` là lần chạy cuối sau khi sửa timeout Redis, timeout upstream và route readiness.

## Chạy lại

Từ gốc repo trong Ubuntu WSL2 với Docker Desktop đang chạy:

```bash
.venv/bin/python scripts/run_cp1_cp4.py cp1
docker build --progress=plain -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker build --progress=plain -f 02-docker/production/Dockerfile -t my-agent:advanced .
.venv/bin/python scripts/run_cp1_cp4.py cp2
.venv/bin/python scripts/run_cp1_cp4.py cp3
.venv/bin/python scripts/run_cp1_cp4.py cp4
```

Runner tạo key/JWT demo trong memory, che giá trị trước khi lưu log và dừng server khi xong. Mỗi lần chạy ghi lại transcript/summary của checkpoint tương ứng. Runner dùng project `k5-day14-docker`, `k5-day14-scaling`, từ chối chạy nếu project đã có container, và dọn container/volume lab vừa tạo. Cần các cổng 8000, 80, 443, 8080 trống theo từng giai đoạn.
