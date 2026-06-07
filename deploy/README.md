# 部署 — 前后端分离生产架构

> **后端** Linux 服务器 + systemd · **公网入口** Cloudflare Tunnel · **前端** Vercel
>
> 本目录把整套生产部署所需的脚本、systemd unit、配置模板和详细文档全部归在一处。
> 三块各有独立 README,但建议先读完本文(架构 + 顺序 + 关键决策)再分头看。

## 架构

```
                                                            ┌────────────────────────┐
                                                            │   Vercel Edge CDN      │
                                                            │  novel.your-domain.com │
                              ┌─────────── 浏览器 ─────────► │  (静态 SPA, dist/)    │
                              │                             └─────────────┬──────────┘
                              │                                           │ fetch
                              │                                           │ VITE_API_BASE
                              │                                           ▼
                              │                          ┌─────────────────────────────────┐
                              │                          │  Cloudflare 边缘                │
                              │                          │  api.novel.your-domain.com      │
                              │                          │  (TLS 终止 + DDoS + Access)     │
                              │                          └─────────────┬───────────────────┘
                              │                                        │ outbound-only
                              │                                        │ QUIC/HTTP2
                              │                                        ▼
                              │           ┌──────────────────────────────────────────────┐
                              │           │  Linux 服务器  (无入站端口)                  │
                              │           │                                              │
                              │           │  ┌──── systemd: cloudflared.service ─────┐   │
                              │           │  │  cloudflared (tunnel daemon)          │   │
                              │           │  └────────────────┬──────────────────────┘   │
                              │           │                   │ http://127.0.0.1:8762    │
                              │           │                   ▼                          │
                              │           │  ┌──── systemd: novel-agent.service ─────┐   │
                              │           │  │  uvicorn / FastAPI                    │   │
                              │           │  │  9 Agent + 7 阶段 Tick 调度           │   │
                              │           │  │  backend/data/ (SQLite, chroma, ...) │   │
                              │           │  └───────────────────────────────────────┘   │
                              │           └──────────────────────────────────────────────┘
                              │
                              └── 直接访问 https://novel.your-domain.com (Vercel)
                                  → 后端走 fetch → CF Tunnel → 127.0.0.1:8762
```

**核心约束**:
- 后端 **不开** 任何入站端口,所有公网流量通过 Cloudflare Tunnel 反向接入
- 前端不和后端同源,跨域走 CORS,**后端必须把 Vercel 域名列入 `cors_origins`**
- SSE(`/api/generate/stream`)直接走 CF Tunnel,**不要** 在 Vercel 上 rewrite 后端 API

## 域名规划

建两个二级域名(都托管在 Cloudflare DNS):

| 域名 | 指向 | 用途 |
|------|------|------|
| `novel.your-domain.com` | Vercel | 前端 SPA |
| `api.novel.your-domain.com` | Cloudflare Tunnel(自动 CNAME 到 `<uuid>.cfargotunnel.com`) | 后端 API |

Vercel 域名 CNAME → `cname.vercel-dns.com`。
后端域名 CNAME 由 `cloudflared tunnel route dns` 一条命令自动建立,不用手动改。

## 部署顺序

**A → B → C**,顺序不能颠倒(后端没起来时 Tunnel 起不来,前端也没法测 CORS)。

### A. 后端 Linux + systemd  →  [`backend/README.md`](./backend/README.md)

```bash
sudo git clone <repo> /opt/novel_auto
sudo bash /opt/novel_auto/deploy/backend/install.sh
sudo -e /opt/novel_auto/.env             # 填 DEEPSEEK_API_KEY
sudo -e /opt/novel_auto/config.json      # 写 cors_origins
sudo systemctl start novel-agent
curl http://127.0.0.1:8762/api/health    # ← 这一步通过再进下一步
```

### B. Cloudflare Tunnel  →  [`cloudflared/README.md`](./cloudflared/README.md)

```bash
sudo bash /opt/novel_auto/deploy/cloudflared/install.sh
# 提示登录 → 浏览器授权
# 提示输入 hostname → api.novel.your-domain.com
sudo cloudflared tunnel route dns novel-agent api.novel.your-domain.com
sudo systemctl start cloudflared
curl -i https://api.novel.your-domain.com/api/health   # ← 公网验证
```

### C. Vercel 前端  →  [`frontend/README.md`](./frontend/README.md)

1. Vercel 控制台 → New Project → 选这个仓库
2. **Root Directory = `frontend`**
3. Environment Variables:
   ```
   VITE_API_BASE=https://api.novel.your-domain.com
   VITE_BASE_PATH=/
   ```
4. Deploy。回头去后端 `config.json` 的 `cors_origins` 加上 Vercel 给的域名,重启后端。

## 目录速查

```
deploy/
├── README.md                                # ← 你在这
├── backend/                                 # Linux + systemd
│   ├── README.md
│   ├── install.sh                           # 首次安装(交互最少)
│   ├── update.sh                            # git pull + restart
│   ├── backup.sh                            # 备份 data/ 到 /var/backups/
│   ├── novel-agent.service                  # systemd unit (含沙箱加固)
│   ├── env.production.example               # → /opt/novel_auto/.env 模板
│   ├── config.production.example.json       # → config.json 模板
│   └── nginx-novel-agent.conf               # 备选: 不用 CF Tunnel 时的 nginx 反代
├── cloudflared/                             # Cloudflare Tunnel
│   ├── README.md
│   ├── install.sh                           # cloudflared + tunnel create + systemd
│   ├── config.yml.example                   # → /etc/cloudflared/config.yml
│   └── cloudflared.service                  # systemd unit
└── frontend/                                # Vercel
    ├── README.md
    ├── vercel.json                          # SPA rewrites + 安全头 + 缓存
    └── env.production.example               # Vercel env 模板
```

## 关键决策与不变量

| 决策 | 为什么 |
|------|--------|
| 后端 bind `127.0.0.1` 不 bind `0.0.0.0` | 不暴露 8762,CF Tunnel 走本地回环 |
| 不让 Vercel rewrites 反代后端 | Vercel rewrite 超时短,SSE 直接断 |
| `cors_origins` 显式列白而不是 `["*"]` | 防止任意网站调你的 API,尤其有写操作端点 |
| `.env` 600,`config.json` 644 | API Key 只对 root 可读 |
| systemd 加 `ProtectSystem=strict` + `ReadWritePaths` | 沙箱化,即使 RCE 也只能写 `data/` |
| 前后端跨域而非同源 | SSE 长连接走 CF 直连,延迟低、不被 CDN 截断 |
| `VITE_BASE_PATH` 可配置 | 同一个 codebase 既能在 FastAPI mount 到 `/nw/`,也能在 Vercel 跑根路径 |

## 整体排错速查

| 故障层 | 看哪里 |
|--------|--------|
| 后端起不来 | `journalctl -u novel-agent -n 100` |
| 公网 curl 不通 | `journalctl -u cloudflared -f` + `cloudflared tunnel info novel-agent` |
| Vercel 调 API CORS 错 | `config.json.cors_origins` + `systemctl restart novel-agent` |
| 前端白屏 | F12 Network,查 `assets/*` 路径 → `VITE_BASE_PATH=/` 没设 |
| SSE 一段时间断 | 看 [`cloudflared/README.md`](./cloudflared/README.md) 第 3 节 — `keepAliveTimeout` |
| 备份 SQLite 不一致 | `systemctl stop novel-agent` 再 `backup.sh` 再 `start` |

## CI/CD(可选,不必)

- 后端:推 main → GitHub Actions SSH 进服务器跑 `update.sh`
- 前端:Vercel 已经自动跟 git,推 main → 自动 deploy
- 真要自动化建议先把 staging 环境拉起来,生产留手动按钮

## 监控建议

最小集合:

1. **后端健康**:`curl https://api.novel.your-domain.com/api/health` 加进 Uptime Robot
2. **磁盘水位**:`/opt/novel_auto/backend/data` 会随 tick 持续增长,
   chroma 索引能上 GB。定期看 `du -sh`
3. **journalctl 体积**:`journalctl --disk-usage`,默认 4GB rotate 够用
4. **LLM 费用**:DeepSeek / MiMo 控制台看 daily token 消耗 — 9 Agent 跑起来不便宜

## 进阶 — 不用 Cloudflare 的备选方案

如果不能/不想用 CF Tunnel(地区受限、合规要求、想自托管 TLS):

1. 用 [`backend/nginx-novel-agent.conf`](./backend/nginx-novel-agent.conf) 起 nginx 反代
2. Let's Encrypt(certbot)申请证书
3. ufw / iptables 只放 443、22
4. 把前端 `VITE_API_BASE` 指到 `https://api.novel.your-domain.com`(直接打 nginx)

注意 nginx 反代 SSE 需要 `proxy_buffering off` + `proxy_read_timeout 300s`,
配置文件里已经写好。
