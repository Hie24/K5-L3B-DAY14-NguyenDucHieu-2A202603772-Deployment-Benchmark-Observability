# CP8 — Observability evidence

Số liệu và phân tích của lần chạy CP8 được ghi tại [BENCHMARK_REPORT.md](../../BENCHMARK_REPORT.md), mục 4–6; AI log ghi phần thực hiện bởi Antigravity.

- Hai CSV gốc: [scale_1_stats.csv](../../benchmark-results/scale_1_stats.csv), [scale_3_stats.csv](../../benchmark-results/scale_3_stats.csv). Bản nộp khớp từng byte với bản trong production/benchmark-results.
- Ảnh [Grafana](../../screenshots/grafana-dashboard.png), [trace chậm](../../screenshots/jaeger-slow-trace.png), [trace lỗi](../../screenshots/jaeger-error-trace.png), [Prometheus alerts](../../screenshots/prometheus-alert-firing.png).
- Ảnh Prometheus thấy đồng thời LLMCostBurnRateHigh, AgentHighErrorRate và AgentInstanceDown firing.
- Báo cáo có trace_id `24f4d90cd488cd82acc157c9b5effb5e`, log JSON cùng trace_id và phân tích span LLM chiếm phần lớn thời gian.
- [alert-rules-test.txt](alert-rules-test.txt): output kiểm lại bằng `prom/prometheus:v3.16.0`, `promtool test rules /p/alert_rules_test.yml`, kết quả SUCCESS.

[submission-audit.json](../submission-audit.json) đối chiếu số trong bảng scaling với CSV và kiểm sự hiện diện/định dạng bảy ảnh. Các ảnh cũng đã được mở để kiểm trực quan khi hoàn thiện hồ sơ.
