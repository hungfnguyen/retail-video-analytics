FROM minio/minio:latest

EXPOSE 9000 9001
VOLUME ["/data"]

# Lệnh khởi động MinIO; credentials phải cung cấp khi chạy container
CMD ["server", "/data", "--console-address", ":9001"]
