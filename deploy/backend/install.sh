#!/usr/bin/env bash
# ============================================================
# novel_auto 后端首次安装脚本 (Debian/Ubuntu 22.04+, RHEL/Rocky 9+)
# 干净机器 → 服务可启动, 但 .env / config.json 中的 API Key 仍需手动填
#
# 用法:
#   sudo bash install.sh                    # 默认安装到 /opt/novel_auto
#   sudo INSTALL_DIR=/srv/novel bash install.sh
#   sudo NOVEL_REPO=https://github.com/your-org/novel_auto.git bash install.sh
# ============================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/novel_auto}"
SERVICE_USER="${SERVICE_USER:-novel}"
SERVICE_GROUP="${SERVICE_GROUP:-novel}"
NOVEL_REPO="${NOVEL_REPO:-}"           # 留空表示已手动 git clone, 跳过 clone
PYTHON_BIN="${PYTHON_BIN:-python3.11}" # 项目要求 3.10+
SERVICE_NAME="novel-agent"

log()  { printf '\033[1;36m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$EUID" -eq 0 ] || die "请用 root / sudo 运行"

# ---------- 1. 系统依赖 ----------
log "安装系统依赖..."
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y --no-install-recommends \
    git curl ca-certificates "$PYTHON_BIN" "${PYTHON_BIN}-venv" "${PYTHON_BIN}-dev" \
    build-essential pkg-config
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y git curl python3.11 python3.11-devel gcc gcc-c++ make
else
  die "未识别的包管理器, 请手动安装: git, $PYTHON_BIN, gcc"
fi

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "找不到 $PYTHON_BIN; 请改 PYTHON_BIN= 重试"

# ---------- 2. 服务账号 ----------
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  log "创建服务账号 $SERVICE_USER ..."
  useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" "$SERVICE_USER"
fi

# ---------- 3. 拉代码 ----------
mkdir -p "$INSTALL_DIR"
if [ -n "$NOVEL_REPO" ] && [ ! -d "$INSTALL_DIR/.git" ]; then
  log "git clone $NOVEL_REPO → $INSTALL_DIR ..."
  git clone "$NOVEL_REPO" "$INSTALL_DIR"
fi
[ -f "$INSTALL_DIR/run.py" ] || die "$INSTALL_DIR 不像项目根目录 (没有 run.py); \
请先手动 git clone, 或设置 NOVEL_REPO=..."

# ---------- 4. venv + 依赖 ----------
if [ ! -d "$INSTALL_DIR/.venv" ]; then
  log "创建虚拟环境 .venv ..."
  "$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip wheel
log "安装 requirements.txt (这一步会下载 chromadb / sentence-transformers, 几分钟)..."
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# ---------- 5. 配置文件 ----------
if [ ! -f "$INSTALL_DIR/.env" ]; then
  log "拷贝 .env 模板 → $INSTALL_DIR/.env (记得填 DEEPSEEK_API_KEY!)"
  cp "$INSTALL_DIR/deploy/backend/env.production.example" "$INSTALL_DIR/.env"
fi
if [ ! -f "$INSTALL_DIR/config.json" ]; then
  log "拷贝 config.json 模板 → 记得改 cors_origins 中的 Vercel 域名!"
  cp "$INSTALL_DIR/deploy/backend/config.production.example.json" "$INSTALL_DIR/config.json"
fi

# ---------- 6. 数据目录 ----------
mkdir -p "$INSTALL_DIR/backend/data" "$INSTALL_DIR/data"

# ---------- 7. 权限 ----------
log "chown $SERVICE_USER:$SERVICE_GROUP → $INSTALL_DIR ..."
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/.env"
chmod 644 "$INSTALL_DIR/config.json"

# ---------- 8. systemd ----------
log "安装 systemd unit → /etc/systemd/system/$SERVICE_NAME.service ..."
install -m 0644 "$INSTALL_DIR/deploy/backend/novel-agent.service" \
  "/etc/systemd/system/$SERVICE_NAME.service"

# 若用户改了 INSTALL_DIR / SERVICE_USER, 自动 sed
if [ "$INSTALL_DIR" != "/opt/novel_auto" ] || [ "$SERVICE_USER" != "novel" ]; then
  sed -i \
    -e "s|/opt/novel_auto|$INSTALL_DIR|g" \
    -e "s|^User=novel$|User=$SERVICE_USER|" \
    -e "s|^Group=novel$|Group=$SERVICE_GROUP|" \
    "/etc/systemd/system/$SERVICE_NAME.service"
fi

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

cat <<EOF

\033[1;32m[install]\033[0m 系统层安装完成。下一步:

  1. 编辑配置文件填入凭据:
       sudo -e $INSTALL_DIR/.env             # DEEPSEEK_API_KEY = ...
       sudo -e $INSTALL_DIR/config.json      # server.cors_origins = ["https://你的-vercel-域名"]

  2. 启动服务:
       sudo systemctl start $SERVICE_NAME
       sudo systemctl status $SERVICE_NAME
       journalctl -u $SERVICE_NAME -f

  3. 验证本地:
       curl http://127.0.0.1:8762/api/health

  4. 装 cloudflared 把 127.0.0.1:8762 通到公网:
       见 deploy/cloudflared/README.md

EOF
