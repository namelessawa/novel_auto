# 部署 — 前后端分离生产架构

> **后端** Windows + Docker(主推) 或 Linux + systemd(备选)
> · **公网入口** Cloudflare Tunnel(Token 模式)
> · **前端** Vercel
>
> 三块各有独立 README,先读完本文(架构 + 顺序 + 关键决策)再分头看。

## 推荐架构(Docker)

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
                              │     ┌────────────────────────────────────────────────────────┐
                              │     │  Windows (or Linux) 宿主机   docker-compose            │
                              │     │                                                        │
                              │     │  ┌──── container: novel-auto-cloudflared ─────┐        │
                              │     │  │  cloudflare/cloudflared (token mode)       │        │
                              │     │  └──────────────────┬─────────────────────────┘        │
                              │     │                     │ http://backend:8762 (docker net) │
                              │     │                     ▼                                  │
                              │     │  ┌──── container: novel-auto-backend ────────┐         │
                              │     │  │  uvicorn / FastAPI                        │         │
                              │     │  │  9 Agent + 7 阶段 Tick 调度               │         │
                              │     │  │  bind-mount: ./data/ ↔ /app/backend/data  │         │
                              │     │  └───────────────────────────────────────────┘         │
                              │     │       ▲                                                │
                              │     │       │ 127.0.0.1:8762 (本机调试用, 不公网暴露)        │
                              │     └───────┼────────────────────────────────────────────────┘
                              │             │
                              └── 直接访问 https://novel.your-domain.com (Vercel)
                                  → 后端走 fetch → CF 边缘 → cloudflared 容器 → backend 容器
```

**核心约束**:
- 后端 **不开** 任何入站端口,所有公网流量通过 Cloudflare Tunnel 反向接入
- 前端不和后端同源,跨域走 CORS,**后端必须把 Vercel 域名列入 `cors_origins`**
- SSE(`/api/generate/stream`)直接走 CF Tunnel,**不要** 在 Vercel 上 rewrite 后端 API
- Docker bind mount 把 `data/` 留在宿主机,容器删了不丢业务数据

## 域名规划

建两个二级域名(都托管在 Cloudflare DNS):

| 域名 | 指向 | 用途 |
|------|------|------|
| `novel.your-domain.com` | Vercel | 前端 SPA |
| `api.novel.your-domain.com` | Cloudflare Tunnel(自动 CNAME 到 `<uuid>.cfargotunnel.com`) | 后端 API |

Vercel 域名 CNAME → `cname.vercel-dns.com`。
后端域名 CNAME 在 CF Tunnel 网页 Public Hostname 那里自动建,**不用手动改 DNS**。

## 部署顺序(推荐 — Docker)

**A → B → C**,顺序不能颠倒。

### A. 后端 + Tunnel(Windows Docker)  →  [`docker/README.md`](./docker/README.md)

```powershell
# Windows PowerShell, 项目根
copy deploy\docker\env.production.example .env
copy deploy\docker\config.production.example.json config.json
notepad .env                # 填 DEEPSEEK_API_KEY 和 CLOUDFLARED_TOKEN
notepad config.json         # 写 cors_origins (先 ["*"] 通起来)
mkdir data\backend, data\storage, data\hf_cache
docker compose -f deploy/docker/docker-compose.yml --env-file .env up -d --build
curl http://127.0.0.1:8762/api/health   # ← 本地验证, 通过才进下一步
```

然后在 Cloudflare 网页 → Tunnel → Public Hostname 配 `api.novel.your-domain.com → http://backend:8762`,公网验证:

```powershell
curl https://api.novel.your-domain.com/api/health
```

### B. Vercel 前端  →  [`frontend/README.md`](./frontend/README.md)

1. Vercel 控制台 → New Project → 选这个仓库
2. **Root Directory = `frontend`**
3. Environment Variables:
   ```
   VITE_API_BASE=https://api.novel.your-domain.com
   ```
4. Deploy。拿到 Vercel 域名后回去 `config.json` 的 `cors_origins` 加上 Vercel 域名,
   `docker compose restart backend` 重启后端让 CORS 生效。

### C. 收紧 CORS

```json
"cors_origins": [
  "https://novel.your-domain.com",
  "https://novel-frontend.vercel.app"
]
```

`docker compose -f deploy/docker/docker-compose.yml restart backend`

## 备选:Linux 服务器 + systemd 裸装

如果你想跑在 Linux VPS 上而不是 Windows Docker,见:

- 后端:[`backend/README.md`](./backend/README.md)(systemd + 沙箱加固 + install.sh)
- Tunnel:[`cloudflared/README.md`](./cloudflared/README.md)(本机装 cloudflared + config 模式)

部署顺序仍是 A → B → C,只是 A 那段换成裸装 systemd。前端 Vercel 部分一致。

## 目录速查

```
deploy/
├── README.md                                # ← 你在这
├── docker/                                  # 主推: 跨平台 Docker
│   ├── README.md                            # Windows 详细步骤
│   ├── Dockerfile                           # python:3.11-slim + 非 root + healthcheck
│   ├── docker-compose.yml                   # backend + cloudflared 编排
│   ├── .dockerignore                        # 排除 data/ / .venv / .git / old / node_modules
│   ├── env.production.example               # → 项目根 .env 模板
│   └── config.production.example.json       # → 项目根 config.json 模板
├── backend/                                 # 备选: Linux + systemd 裸装
│   ├── README.md
│   ├── install.sh / update.sh / backup.sh
│   ├── novel-agent.service                  # 沙箱化 systemd unit
│   ├── env.production.example
│   ├── config.production.example.json
│   └── nginx-novel-agent.conf               # 备选: 不走 CF Tunnel 时的 nginx 反代
├── cloudflared/                             # 备选: Linux 上裸装 cloudflared (config 模式)
│   ├── README.md
│   ├── install.sh
│   ├── config.yml.example
│   └── cloudflared.service
└── frontend/                                # Vercel (无变化)
    ├── README.md
    ├── vercel.json
    └── env.production.example
```

## Docker vs Linux+systemd 怎么选

| 维度 | Docker | Linux + systemd |
|------|--------|-----------------|
| 跨平台 | ✅ Windows / macOS / Linux 同一套 | 只 Linux |
| 部署节奏 | `docker compose up -d` 一条命令 | 4 步 install.sh + 改配置 |
| 升级 | `git pull && up -d --build`(增量,~2 分钟) | `update.sh`,本地 pip 升级 |
| 启停 | `docker compose restart` | `systemctl restart` |
| 隔离 | 容器级 | 进程级(systemd 沙箱) |
| 资源开销 | Docker Desktop 自身 ~1 GB RAM | 直接跑,无壳子 |
| Windows 长开机 | 笔记本要禁睡眠,生产建议台式 / 小主机 | 不适用(在 Linux 服务器上) |
| 备份 | `tar data\` 一个目录 | `tar backend/data` |

**默认选 Docker** — 部署链路最短、跨平台、依赖只有 Docker Desktop。
**只有当你已经有 Linux VPS、要长期稳定运行**,再走 systemd 路线。

## 关键决策与不变量

| 决策 | 为什么 |
|------|--------|
| 后端只 bind `127.0.0.1:8762` | 不公网暴露 8762,Cloudflared 走 docker 内网或回环 |
| 不让 Vercel rewrites 反代后端 | Vercel rewrite 超时短,SSE 直接断 |
| `cors_origins` 显式列白而非 `["*"]` | 防止任意网站调你的 API(尤其有 PUT/POST 端点) |
| 数据走 bind mount 不是 image | 容器 rebuild 不会丢业务数据 |
| 容器内非 root(uid 1001) | RCE 提权门槛 |
| `config.json` `:ro` mount | 容器内代码不能改宿主机配置 |
| Cloudflared 用 Token 模式 | 路由配置在网页,改路由不用重启容器 |
| 前后端跨域而非同源 | SSE 长连接直连 CF,不被 Vercel 截断 |

## 整体排错速查

| 故障层 | 看哪里 |
|--------|--------|
| backend 容器起不来 | `docker compose -f deploy/docker/docker-compose.yml logs backend` |
| cloudflared 起不来 | `docker compose logs cloudflared` — `Tunnel credentials are invalid` = token 错 |
| 本地 curl 不通 | 看 backend 容器 healthcheck:`docker ps`,`(healthy)` 状态;还在 `starting` 说明模型还在下 |
| 公网 curl 502 | CF 网页 Public Hostname 的 URL 没填 `backend:8762`,改成 `localhost:8762` 不对 |
| Vercel 调 API CORS 错 | `config.json.cors_origins` + `docker compose restart backend` |
| 前端白屏 | F12 Network,查 `assets/*` 路径 |
| 备份 SQLite 不一致 | `docker compose stop backend` 再 tar |

## CI/CD(可选,不必)

- 后端:推 main → GitHub Actions 触发宿主机 docker compose up -d --build
- 前端:Vercel 已经自动跟 git,推 main → 自动 deploy
- 真要自动化建议先把 staging 环境拉起来,生产留手动按钮

## 监控建议

最小集合:

1. **后端健康**:`curl https://api.novel.your-domain.com/api/health` 加进 Uptime Robot
2. **磁盘水位**:`data\backend\` 会随 tick 持续增长,chroma 索引能上 GB。定期 `Get-ChildItem -Recurse | Measure-Object -Property Length -Sum`
3. **Docker 资源**:Docker Desktop → Containers / Resources 看 CPU/RAM
4. **LLM 费用**:DeepSeek / MiMo 控制台看 daily token 消耗 — 9 Agent 跑起来不便宜
