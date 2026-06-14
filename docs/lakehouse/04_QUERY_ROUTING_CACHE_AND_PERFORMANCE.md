# Query Routing Cache And Performance

Tài liệu này chốt cách analyst layer nên query dữ liệu sau khi thống nhất lại kiến trúc.

## 1. Routing rule

### Live path

`Live UI` không đi qua Trino.

Nó nên đọc:

- Redis realtime state
- runtime media metadata

### Analyst path

`Analyst UI` không nên query Silver mặc định.

Nó nên đọc:

- Gold facts nếu đủ nhỏ và đúng grain
- Gold serving tables nếu cần serving riêng

### Debug path

Chỉ khi debug hoặc drill-down mới đọc:

- `silver_*`
- `bronze_*`

## 2. Source rule theo màn hình

| Use case | Source đúng |
|---|---|
| Live current count | Redis |
| Live queue/zone status | Redis |
| Dashboard traffic | Gold facts hoặc Gold serving traffic |
| Heatmap history | Gold serving heatmap |
| Queue analytics | Gold facts queue hoặc Gold serving queue |
| Zone analytics | Gold facts zone hoặc Gold serving zone |
| Alert history | `gold_alerts` hoặc Gold serving alert |
| Alert aggregate widgets | `gold_alert_events` hoặc Gold serving alert |
| Debug detection | Silver |

## 3. Cache rule

Cache vẫn rất quan trọng, dù có Gold serving.

Lý do:

- Trino vẫn là remote query engine
- Iceberg vẫn là snapshot storage trên S3
- dashboard có cùng query lặp lại nhiều lần

Nên giữ:

- API cache ở FastAPI/Redis
- TTL ngắn cho dashboard
- TTL dài hơn cho heatmap history

## 4. Performance rule

Nếu dashboard chậm, thứ tự kiểm tra nên là:

1. query có đang đọc đúng bảng không
2. có đang đọc Silver sai chỗ không
3. có cache không
4. file count / snapshot count của Iceberg
5. Trino single-node có đang scan quá rộng không

Không được mặc định nhảy ngay vào kiến trúc mới nếu:

- cache đủ giải quyết
- Gold facts đã đủ dùng

## 5. Gold serving chỉ được thêm khi có lý do

Gold serving nên được thêm khi:

- query từ Gold facts vẫn nặng
- grain của Gold facts không khớp analyst use case
- cần bounded batch table ổn định hơn cho dashboard

Nếu Gold facts đã đủ nhỏ và đúng grain, không cần thêm serving table riêng.

## 6. Maintenance rule

Maintenance là một phần bắt buộc của lakehouse production:

- optimize
- manifest cleanup
- snapshot retention
- orphan cleanup
- analyze

Nhưng maintenance không đổi kiến trúc:

```text
maintenance giữ table khỏe,
không thay vai trò của Flink hay Airflow
```

## 7. Kết luận

Routing đúng cho project này là:

```text
Live -> Redis
Analyst -> Gold facts / Gold serving
Debug -> Silver / Bronze
```

Và cache vẫn là lớp tối ưu đầu tiên trước khi nghĩ tới thay đổi mô hình dữ liệu.
