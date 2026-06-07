#!/usr/bin/env bash
# ============================================================
# 在 Linux 服务器上装 cloudflared + 注册一个 tunnel + 装 systemd
#
# 前置: 你已经登录 Cloudflare, 域名托管在 Cloudflare DNS
# 用法: sudo bash install.sh
#   - 第一次会提示浏览器登录 (拷贝链接到本地浏览器打开授权)
#   - 之后会创建一个名为 novel-agent 的 tunnel, 生成凭据 JSON
#   - DNS 路由 (api.novel.example.com → tunnel) 需要你手动跑一条命令, 见末尾提示
# ============================================================
set -euo pipefail

TUNNEL_NAME="${TUNNEL_NAME:-novel-agent}"
HOSTNAME="${HOSTNAME:-}"        # api.novel.your-domain.com — 不填脚本会问你

log()  { printf '\033[1;36m[cf]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$EUID" -eq 0 ] || die "请用 root / sudo 运行"

# ---------- 1. 装 cloudflared 二进制 ----------
if ! command -v cloudflared >/dev/null 2>&1; then
  log "下载 cloudflared (Cloudflare 官方仓库)..."
  ARCH=$(dpkg --print-architecture 2>/dev/null || rpm --eval '%{_arch}' 2>/dev/null || uname -m)
  case "$ARCH" in
    amd64|x86_64) PKG_ARCH=amd64 ;;
    arm64|aarch64) PKG_ARCH=arm64 ;;
    *) die "不支持的架构: $ARCH" ;;
  esac
  if command -v apt-get >/dev/null 2>&1; then
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
      | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
      | tee /etc/apt/sources.list.d/cloudflared.list
    apt-get update -y
    apt-get install -y cloudflared
  elif command -v dnf >/dev/null 2>&1; then
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$PKG_ARCH.rpm" \
      -o /tmp/cloudflared.rpm
    dnf install -y /tmp/cloudflared.rpm
    rm -f /tmp/cloudflared.rpm
  else
    die "未识别的包管理器, 请手动装 cloudflared"
  fi
fi
log "cloudflared 已安装: $(cloudflared --version 2>&1 | head -1)"

# ---------- 2. 登录 Cloudflare ----------
mkdir -p /etc/cloudflared
if [ ! -f /root/.cloudflared/cert.pem ]; then
  log "第一次登录: 等下会打印一个 https URL, 拷到浏览器授权 (选你的域名 zone)..."
  cloudflared tunnel login
fi

# ---------- 3. 创建 tunnel ----------
if cloudflared tunnel list 2>/dev/null | awk 'NR>2 {print $2}' | grep -qx "$TUNNEL_NAME"; then
  log "tunnel '$TUNNEL_NAME' 已存在, 跳过 create"
else
  log "创建 tunnel '$TUNNEL_NAME' ..."
  cloudflared tunnel create "$TUNNEL_NAME"
fi

# 提取 UUID + 凭据
TUNNEL_UUID=$(cloudflared tunnel list 2>/dev/null | awk -v n="$TUNNEL_NAME" 'NR>2 && $2==n {print $1; exit}')
[ -n "$TUNNEL_UUID" ] || die "拿不到 tunnel UUID"

SRC_CRED="/root/.cloudflared/$TUNNEL_UUID.json"
DST_CRED="/etc/cloudflared/$TUNNEL_UUID.json"
if [ -f "$SRC_CRED" ] && [ ! -f "$DST_CRED" ]; then
  install -m 0600 "$SRC_CRED" "$DST_CRED"
fi
[ -f "$DST_CRED" ] || die "找不到凭据 $DST_CRED — 可能 create 失败"

# ---------- 4. 落 config.yml ----------
HERE="$(dirname "$(readlink -f "$0")")"
if [ ! -f /etc/cloudflared/config.yml ]; then
  log "拷贝 config.yml 模板 → /etc/cloudflared/config.yml"
  install -m 0644 "$HERE/config.yml.example" /etc/cloudflared/config.yml
fi

# 替换占位 UUID + 凭据路径
sed -i \
  -e "s|00000000-0000-0000-0000-000000000000|$TUNNEL_UUID|g" \
  /etc/cloudflared/config.yml

# 询问 hostname
if [ -z "$HOSTNAME" ]; then
  read -rp "请输入要绑定的 hostname (例如 api.novel.example.com): " HOSTNAME
fi
[ -n "$HOSTNAME" ] || die "hostname 不能为空"
sed -i "s|api.novel.your-domain.com|$HOSTNAME|g" /etc/cloudflared/config.yml

# ---------- 5. systemd ----------
log "安装 systemd unit ..."
install -m 0644 "$HERE/cloudflared.service" /etc/systemd/system/cloudflared.service
mkdir -p /var/log/cloudflared
systemctl daemon-reload
systemctl enable cloudflared

cat <<EOF

\033[1;32m[cf]\033[0m cloudflared 安装完成。下一步:

  1. 创建 DNS 路由 (把 $HOSTNAME 指向这个 tunnel):
       sudo cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME"

  2. 启动:
       sudo systemctl start cloudflared
       sudo systemctl status cloudflared
       journalctl -u cloudflared -f

  3. 验证:
       curl -i https://$HOSTNAME/api/health
       期望: {"name":"AI 长篇小说生成 Agent 系统",...}

  4. 把这个 hostname 填到 Vercel 的 VITE_API_BASE:
       VITE_API_BASE=https://$HOSTNAME

  config.yml: /etc/cloudflared/config.yml
  凭据:       $DST_CRED  (chmod 600)
  tunnel UUID: $TUNNEL_UUID

EOF
