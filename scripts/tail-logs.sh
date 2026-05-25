#!/usr/bin/env bash
# Tail logs của tất cả container hoặc 1 container cụ thể.
# Usage:
#   ./scripts/tail-logs.sh              # tất cả container (follow)
#   ./scripts/tail-logs.sh pulsar       # chỉ container chứa "pulsar" trong tên
#   ./scripts/tail-logs.sh -n 50        # 50 dòng cuối của tất cả, không follow
set -euo pipefail

if [ $# -eq 0 ]; then
    # Tất cả container
    docker compose logs -f --tail=20
elif [ "$1" = "-n" ]; then
    # N dòng cuối, không follow
    shift
    docker compose logs --tail="$1"
else
    # Container cụ thể
    docker compose logs -f --tail=20 "$@"
fi
