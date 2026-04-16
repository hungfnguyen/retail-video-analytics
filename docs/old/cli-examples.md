# CLI Examples - Pulsar Commands

Các lệnh CLI hữu ích để làm việc với Pulsar trong dự án Retail Video Analytics.

## List Topics

Liệt kê tất cả topics trong namespace:

```bash
bin/pulsar-admin topics list retail/metadata
```

## Consume Messages

Consume và xem nội dung messages từ topic:

```bash
bin/pulsar-client consume \
  persistent://retail/metadata/events \
  -s "view-data-sub5" -n 1 -p Earliest \
  | grep -o '{"schema_version.*}' \
  | python3 -m json.tool
```

### Parameters
- `-s`: Subscription name
- `-n`: Number of messages to consume (1 = chỉ đọc 1 message)
- `-p`: Start position (Earliest = từ đầu topic, Latest = chỉ messages mới)

## Useful Commands

### Check Topic Stats
```bash
bin/pulsar-admin topics stats persistent://retail/metadata/events
```

### Reset Subscription
```bash
bin/pulsar-admin topics reset-cursor \
  persistent://retail/metadata/events \
  -s "subscription-name" \
  --position earliest
```

### Delete Topic
```bash
bin/pulsar-admin topics delete persistent://retail/metadata/events
```
