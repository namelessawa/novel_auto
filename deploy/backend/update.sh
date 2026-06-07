#!/usr/bin/env bash
# ============================================================
# 拉取最新代码 + 升级依赖 + 重启服务
# 默认目标: /opt/novel_auto  novel-agent.service
# 用法: sudo bash deploy/backend/update.sh
# 选项: BRANCH=main / SKIP_PIP=1 / NO_RESTART=1
# ============================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/novel_auto}"
SERVICE_NAME="${SERVICE_NAME:-novel-agent}"
BRANCH="${BRANCH:-main}"

log()  { printf '\033[1;36m[update]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$EUID" -eq 0 ] || die "请用 root / sudo 运行"
[ -d "$INSTALL_DIR/.git" ] || die "$INSTALL_DIR 不是 git 仓库"

cd "$INSTALL_DIR"

log "git fetch + checkout $BRANCH ..."
sudo -u "$(stat -c '%U' .git)" git fetch --all --prune
sudo -u "$(stat -c '%U' .git)" git checkout "$BRANCH"
OLD=$(git rev-parse HEAD)
sudo -u "$(stat -c '%U' .git)" git pull --ff-only
NEW=$(git rev-parse HEAD)

if [ "$OLD" = "$NEW" ]; then
  log "无更新, 跳过 pip / restart"
  exit 0
fi
log "更新: $OLD → $NEW"
log "改动: $(git log --oneline "$OLD..$NEW" | wc -l) 个提交"

# 检查 requirements 是否变化, 变化则升级
if [ "${SKIP_PIP:-0}" != "1" ] && ! git diff --quiet "$OLD" "$NEW" -- requirements.txt; then
  log "requirements.txt 有改动, pip install ..."
  "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
fi

if [ "${NO_RESTART:-0}" = "1" ]; then
  log "NO_RESTART=1, 跳过重启"
  exit 0
fi

log "重启 $SERVICE_NAME ..."
systemctl restart "$SERVICE_NAME"
sleep 2
systemctl --no-pager status "$SERVICE_NAME" | head -15

log "等 5 秒做健康检查..."
sleep 5
if curl -fsS http://127.0.0.1:8762/api/health >/dev/null; then
  log "健康检查通过, 部署完成"
else
  die "健康检查失败! journalctl -u $SERVICE_NAME -n 50"
fi
