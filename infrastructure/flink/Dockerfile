# -----------------------------------------------------------------------------
# Stage 1: Build Flink Jobs với Maven
# -----------------------------------------------------------------------------
FROM maven:3.9-eclipse-temurin-11 AS builder

WORKDIR /build

# Copy pom.xml và source code (context là project root)
COPY flink-jobs/java/pom.xml ./
COPY flink-jobs/java/src ./src

# Build JAR (skip tests để nhanh hơn)
RUN mvn clean package -DskipTests

# -----------------------------------------------------------------------------
# Stage 2: Flink Runtime Image với Dependencies đầy đủ
# -----------------------------------------------------------------------------
FROM hungfnguyen28/retail-flink:1.18-v1

ENV FLINK_USR_LIB_DIR=/opt/flink/usrlib

# -----------------------------------------------------------------------------
# Copy Pre-built Jobs từ Builder Stage
# -----------------------------------------------------------------------------
RUN mkdir -p "$FLINK_USR_LIB_DIR"

# Copy compiled JAR từ build stage (cùng một JAR, nhiều tên cho các job)
COPY --from=builder /build/target/silver-job-0.1.0.jar "$FLINK_USR_LIB_DIR/bronze-job.jar"
COPY --from=builder /build/target/silver-job-0.1.0.jar "$FLINK_USR_LIB_DIR/silver-job.jar"
COPY --from=builder /build/target/silver-job-0.1.0.jar "$FLINK_USR_LIB_DIR/gold-job.jar"
COPY --from=builder /build/target/silver-job-0.1.0.jar "$FLINK_USR_LIB_DIR/gold-jobs.jar"

# Copy script tự động submit jobs
COPY infrastructure/flink/scripts/submit-jobs.sh /opt/flink/bin/submit-jobs.sh
RUN chmod +x /opt/flink/bin/submit-jobs.sh

EXPOSE 6123 8081
