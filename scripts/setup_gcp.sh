#!/usr/bin/env bash
# Create GCS bucket and configure lifecycle policy for keyframe storage

set -euo pipefail

PROJECT_ID="${GCS_PROJECT_ID:?Set GCS_PROJECT_ID}"
BUCKET="${GCS_FRAMES_BUCKET:?Set GCS_FRAMES_BUCKET}"
REGION="${GCS_REGION:-us-central1}"
RETENTION_DAYS="${FRAME_RETENTION_DAYS:-7}"

echo "Creating bucket gs://${BUCKET} in project ${PROJECT_ID}..."
gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET}" || true

echo "Applying ${RETENTION_DAYS}-day lifecycle policy..."
cat > /tmp/lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": ${RETENTION_DAYS}}
      }
    ]
  }
}
EOF

gsutil lifecycle set /tmp/lifecycle.json "gs://${BUCKET}"
rm /tmp/lifecycle.json

echo "Enabling uniform bucket-level access..."
gsutil uniformbucketlevelaccess set on "gs://${BUCKET}"

echo "Done. Bucket gs://${BUCKET} is ready."
