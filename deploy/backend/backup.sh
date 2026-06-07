#!/usr/bin/env bash
# ============================================================
# 备份 backend/data/ (tick_state / summary_tree / ticks.db / chroma / 快照 / narratives)
# 默认压缩到 /var/backups/novel-agent/YYYYMMDD-HHMM.tar.zst
# 用法: sudo bash deploy/backend/backup.sh
# 加 cron: 0 4 * * * /opt/novel_auto/deploy/backend/backup.sh
# ============================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/novel_auto}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/novel-agent}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d-%H%M)
OUT="$BACKUP_DIR/novel-data-$TS.tar.zst"

# 选 zstd 而非 gz: chroma 索引很大, zstd 压缩比 + 速度都好。
# 没装 zstd 会回退到 gz。
if command -v zstd >/dev/null 2>&1; then
  tar --use-compress-program='zstd -T0 -19 --long' -cf "$OUT" \
      -C "$INSTALL_DIR" backend/data data 2>/dev/null
else
  OUT="${OUT%.zst}.gz"
  tar -czf "$OUT" -C "$INSTALL_DIR" backend/data data 2>/dev/null
fi

echo "[backup] $OUT ($(du -h "$OUT" | cut -f1))"

# 清理过期
find "$BACKUP_DIR" -name 'novel-data-*.tar.*' -type f -mtime "+$KEEP_DAYS" -delete
echo "[backup] 清理 ${KEEP_DAYS} 天前的备份完毕"
