# Cloudflare Tunnel — 把后端通到公网

> 后端只 bind `127.0.0.1:8762`,**不开任何入站端口**。
> cloudflared 在服务器上跑一个守护进程,主动连 Cloudflare 边缘,
> 边缘把 `https://api.novel.your-domain.com/api/...` 反代到服务器内的 `127.0.0.1:8762`。

## 为什么用 Cloudflare Tunnel

| 优点 | 说明 |
|------|------|
| 无入站端口 | 服务器防火墙可全 deny inbound,只允许 outbound 443 |
| 免运维证书 | TLS 在 CF 边缘终止,本地不用 Let's Encrypt/Caddy |
| 自带 DDoS | 流量先到 CF,再回源 |
| WebSocket / SSE 友好 | CF 原生支持,backend 的 `/api/generate/stream` 直通 |
| 免费 | 个人/小流量场景 free plan 够用 |

代价:绑定到 Cloudflare 生态、流量过 CF(对中国大陆访问会绕)。
若你不想被锁定,见后端 README 的 nginx 替代方案。

## 0. 前置

1. 域名托管在 Cloudflare DNS(在 Cloudflare 控制台已经能看到这个 zone)
2. 你打算给后端起个二级域名,例如 `api.novel.your-domain.com`
3. 服务器上 [`../backend/`](../backend/) 已经装好,`curl http://127.0.0.1:8762/api/health` 能通

## 1. 自动安装(推荐)

```bash
sudo bash /opt/novel_auto/deploy/cloudflared/install.sh
```

脚本会:
1. 装 `cloudflared`(Debian/Ubuntu 用官方 apt 源,RHEL/Rocky 用最新 rpm)
2. `cloudflared tunnel login` — **会打印一个 URL,拷贝到本地浏览器打开授权**
3. 创建 tunnel `novel-agent`,拿到 UUID 和凭据 JSON
4. 凭据 → `/etc/cloudflared/<uuid>.json`(chmod 600)
5. `config.yml` → `/etc/cloudflared/config.yml`(占位 UUID 和 hostname 自动替换)
6. 装 systemd unit,**不自动启动** — 你还得跑下面这条命令做 DNS 路由:

```bash
sudo cloudflared tunnel route dns novel-agent api.novel.your-domain.com
```

这条命令在 Cloudflare DNS 里创建一条 CNAME → `<uuid>.cfargotunnel.com`,
不能省。

然后启动:

```bash
sudo systemctl start cloudflared
journalctl -u cloudflared -f
```

健康检查:

```bash
curl -i https://api.novel.your-domain.com/api/health
# HTTP/2 200
# {"name":"AI 长篇小说生成 Agent 系统","version":"2.0.0","status":"running"}
```

## 2. 手动步骤(如果脚本不合适)

```bash
# 装 cloudflared (Debian/Ubuntu)
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared

# 登录(浏览器打开打印出来的 URL)
cloudflared tunnel login

# 创建 tunnel
cloudflared tunnel create novel-agent
# 输出: Created tunnel novel-agent with id 8a7b6c5d-...
# 凭据落到 ~/.cloudflared/8a7b6c5d-....json

# 搬到系统目录
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/8a7b6c5d-*.json /etc/cloudflared/
sudo chmod 600 /etc/cloudflared/8a7b6c5d-*.json

# 写 config.yml — 改 tunnel UUID / credentials-file / hostname
sudo cp /opt/novel_auto/deploy/cloudflared/config.yml.example /etc/cloudflared/config.yml
sudo nano /etc/cloudflared/config.yml

# DNS 路由
cloudflared tunnel route dns novel-agent api.novel.your-domain.com

# systemd
sudo cp /opt/novel_auto/deploy/cloudflared/cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared
```

## 3. config.yml 关键字段

完整模板见 [`config.yml.example`](./config.yml.example)。重点:

| 字段 | 说明 |
|------|------|
| `tunnel` | tunnel UUID,由 `cloudflared tunnel create` 返回 |
| `credentials-file` | 凭据 JSON 路径,必须 chmod 600 |
| `ingress[0].hostname` | 公网域名,要跟 DNS route 一致 |
| `ingress[0].service` | 内部目标,固定 `http://127.0.0.1:8762` |
| `originRequest.connectTimeout` | 30s — SSE 长连接需要 |
| `originRequest.keepAliveTimeout` | 90s — 比 CF 默认 30s 长 |
| `disableChunkedEncoding: false` | 必须 false,否则 SSE 会被攒着发 |

### SSE / 流式接口注意

backend 的 `/api/generate/stream` 走 `sse-starlette`,有两个坑:

1. **连接保持**:CF 默认 100s 没流量就断开。我们让前端每 ~30s 收一个心跳 event,
   或者把后端 `EventSourceResponse(..., ping=15)` 打开
   (`backend/api/routes.py` 已有 sse-starlette 默认 ping)
2. **不能压缩**:SSE 不能走 gzip,CF 会自动跳过 `text/event-stream`,
   不用手动配,但要确保后端 `Content-Type` 准确

## 4. 进阶 — Cloudflare Access(可选,推荐)

只让登录用户访问 API,而不是任何拿到 URL 的人:

1. CF Dashboard → Zero Trust → Access → Applications → Add Application
2. Self-hosted → Application domain: `api.novel.your-domain.com`
3. Policy:`emails` 列你的邮箱 / Google Workspace / GitHub OAuth
4. Vercel 前端要在 `fetch` 里加 CF Access 的 JWT。
   最简单的做法:浏览器先访问一次域名走 OAuth,之后浏览器会自动带 `CF_Authorization` cookie

不开 Access 也可以,**但务必**:
- `config.json.server.cors_origins` 严格列白
- `PUT /api/config/llm` / `POST /api/reset` 这些写操作端点拉黑,或加 token

## 5. 排错速查

| 现象 | 排查 |
|------|------|
| `cloudflared tunnel login` 卡住 | URL 没拷出来打开。日志最后几行有 `Please open ...` |
| `route dns` 报 `record already exists` | DNS 里同名记录已存在,Cloudflare 面板手动删了再 route |
| 启动后 `journalctl` 报 `failed to dial origin` | 后端没在 `127.0.0.1:8762` 监听,先 `curl http://127.0.0.1:8762/api/health` |
| 公网 curl 报 `1033 Argo Tunnel error` | tunnel 没连上 CF 边缘,看 `journalctl -u cloudflared -f` |
| 前端 fetch 报 `524 timeout` | 长请求超过 100s,需在 origin 服务端拆短,或开 CF Enterprise |
| SSE 一段时间后断 | 后端 `ping=15`,前端做自动重连(EventSource 自带) |
| `403` from CF | Access policy 拦了,或 cookie 没带,或域名拼错 |
| 切换服务器但 hostname 不变 | 在新服务器跑同样 install.sh,**复用** UUID:把旧凭据 json 拷过去即可,DNS 不用动 |

## 6. 卸载

```bash
sudo systemctl disable --now cloudflared
sudo rm -f /etc/systemd/system/cloudflared.service
sudo rm -rf /etc/cloudflared
# 在 Cloudflare 端删除 tunnel
cloudflared tunnel delete novel-agent
# 在 Cloudflare DNS 删 CNAME
# 卸载二进制
sudo apt remove cloudflared    # 或 dnf remove cloudflared
```
