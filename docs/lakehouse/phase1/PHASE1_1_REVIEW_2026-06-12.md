# Phase 1.1 Review & Verification — API Cache

Người đánh giá: Claude (Opus 4.8)
Ngày: 2026-06-12
Đối tượng: `PHASE1_API_CACHE_2026-06-12.md` + code Codex sửa (`analytics.py`, `test_analytics_api.py`).
Phương pháp: đọc diff, chạy test, **verify end-to-end trên stack đang chạy** (phần Codex để mở).

---

## TL;DR

| Hạng mục | Kết luận |
|---|---|
| Thiết kế cache | ✅ Tốt, defensive đúng cách. |
| Redis config | ✅ Giống hệt live endpoints → cùng shared Redis. "Key chưa xuất hiện" chỉ do API chưa reload. |
| Test (9 passed) | ✅ Verify lại OK, cover đúng trọng tâm. |
| **End-to-end runtime** | ✅ **Tôi đã verify — cache CHẠY THẬT.** Dashboard 7.2s → 0.0038s. |

**Kết luận: Phase 1.1 đúng, đã test, và đã verify chạy thật. Sẵn sàng commit.** Open item duy nhất của Codex (verify end-to-end) nay đã đóng.

---

## 1. Review code (PASS)

Đọc diff `services/api/src/rva_api/api/v1/analytics.py`:

- **Chỉ cache `ready` + `empty`, KHÔNG cache `error`** — đúng. `_cacheable_status` lọc, error path return thẳng không set cache.
- **Degrade gracefully**: `_get_cache_client` lazy-init, nếu Redis None → set `_analytics_cache_disabled`, các path get/set bọc `try/except` nuốt lỗi → cache hỏng không bao giờ làm gãy request (không 503). Đúng tinh thần cache.
- **Key namespace**: `analytics:cache:v1:<endpoint>:<params>`. Heatmap gồm `camera_id` + `days` + `metric` → tách đúng theo tham số, không đụng nhau.
- **TTL tách biệt** + override bằng env: dashboard/queue 120s, heatmap 1d 300s / 7d+ 900s, alerts 300s, empty = `min(ready_ttl, 60)`, error 0. `empty` ngắn để không đóng băng trạng thái rỗng lúc warm-up — hợp lý.
- **Round-trip**: `json.dumps(payload)` → `model_validate(json.loads(raw))`. Lossless với payload toàn primitive/list/dict.

### Điểm quan trọng đã kiểm: Redis config

`_cache_config()` **giống hệt** `_redis_config()` của `live.py` (cùng `REDIS_HOST/REDIS_PORT/REDIS_HOST_PORT/REDIS_PASSWORD/REDIS_DB`, default port 16379 host-side / 6379 trong compose). Live endpoints đang chạy được ⇒ cache connect đúng cùng Redis. Việc Codex "chưa thấy key" chỉ vì API process khi đó chưa reload code mới.

---

## 2. Verify test (PASS)

```text
uv run pytest tests/unit/test_analytics_queries.py tests/unit/test_analytics_api.py -> 9 passed
```

`test_analytics_api.py` cover đúng trọng tâm bằng `FakeCache` + monkeypatch:
- dashboard `ready` → cache hit, query builder chỉ chạy 1 lần, TTL = `DASHBOARD_CACHE_TTL_SEC`.
- dashboard `error` → **không** cache, query chạy lại cả 2 lần.
- queue `ready` → cache hit.
- heatmap `empty` → cache với TTL = `EMPTY_RESULT_CACHE_TTL_SEC` (ngắn).

---

## 3. Verify end-to-end runtime (PASS — phần Codex để mở)

API đang chạy host-side: `uvicorn rva_api.main:app --workers 4` (PID start 14:40, đã load code mới). Tôi flush key rồi đo cold/hot:

| Endpoint | Cold | Hot | TTL đo được |
|---|---:|---:|---:|
| `dashboard?days=7` | **7.23s** | **0.0038s** | 117 (≈120) |
| `queue?days=7` | 2.94s | 0.0046s | 120 |
| `heatmap cam_01 1d` | 2.33s | 0.0055s | — |
| `heatmap cam_02 1d` | 0.96s | — | key riêng |

Kiểm tra thêm:
- Hot dashboard body `data_status=ready` (không rỗng/hỏng).
- Heatmap key tách đúng theo camera: `...:heatmap:cam_01:days_1:metric_presence` và `...:cam_02:...` tồn tại song song.
- Không có key `error` nào trong Redis.
- 4 uvicorn workers init client riêng nhưng cùng 1 Redis ⇒ cache **chia sẻ** giữa workers. ✅

→ Cache giảm latency ~**1900x** trên hot path. Người dùng poll 30s sẽ gần như luôn trúng hot.

---

## 4. Ghi nhận thẳng thắn (không phải bug)

- **Cache là lớp che latency, không phải fix gốc.** Cold request đầu vẫn 7s+ và sẽ tăng theo data volume. Doc §7.2 thừa nhận đúng điều này.
- `generated_at` bị "đóng băng" theo lần build đầu khi trả từ cache — hơi lệch ngữ nghĩa nhưng không phá contract. Chấp nhận được.
- Vì vậy **Phase 1.3 (rollup `unique_tracks`) vẫn là việc bắt buộc** để hạ cold latency — phasing của Codex đúng thứ tự.

---

## 5. Chốt cho người dùng

- ✅ **Phase 1.1 đạt. Commit được.** (gộp cùng fix correctness Phase 0 hoặc commit riêng cache.)
- ✅ End-to-end đã verify chạy thật, không cần restart thêm.
- ➡️ Tiếp tục Phase 1.2 (maintenance định kỳ) như Codex đề xuất; nhớ Phase 1.3 mới là đòn xử lý cold path.
