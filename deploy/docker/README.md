# 后端部署 — Windows + Docker Desktop + Cloudflare Tunnel(Token 模式)

> 一条 `docker compose up -d` 把后端 + cloudflared 两个容器都拉起来。
> 后端只 bind 宿主机 `127.0.0.1:8762`,公网入口由同一 docker 网络里的 cloudflared
> 容器代理出去。改路由在 Cloudflare 网页上做,不用重启容器。

## 一句话

```powershell
# Windows PowerShell, 在项目根
copy deploy\docker\env.production.example .env
copy deploy\docker\config.production.example.json config.json
notepad .env         # 填 DEEPSEEK_API_KEY 和 CLOUDFLARED_TOKEN
notepad config.json  # 填 cors_origins
docker compose -f deploy/docker/docker-compose.yml --env-file .env up -d --build
```

---

## 0. 前置

- Windows 10 22H2+ 或 Windows 11
- 已装 **Docker Desktop**(开 WSL2 backend,Settings → General → Use WSL 2 based engine)
- 项目代码已经 `git clone` 到 Windows 本地一个路径(以下用 `E:\pythonproject\novel_auto` 为例,你的路径替换即可)
- Cloudflare 账号 + 一个托管在 Cloudflare DNS 的域名(免费 plan 足够)
- 上游 LLM API Key(DeepSeek / MiMo / 自定义,任选一个填 `.env`)

### Windows 长开机注意

Docker Desktop 默认随系统启动,容器 `restart: unless-stopped` 会自动重启。
但**笔记本休眠 / 注销账户** 后服务会断,生产场景请:

- 设置 → 电源 → "永不睡眠" / "插电时不息屏"
- 任务计划 → 让 Docker Desktop 以系统自启
- 或者用一台台式机 / 小主机常驻

---

## 1. 在 Cloudflare 网页创建 Tunnel,拿 token

1. 浏览器打开 https://one.dash.cloudflare.com/
2. 左栏 **Networks → Tunnels → Create a tunnel**
3. **Cloudflared** → Next
4. 取个名字,例如 `novel-auto` → Save tunnel
5. 安装方式选 **Docker**,页面会展示一条命令:
   ```
   docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token eyJhI...
   ```
   **把 `eyJhI...` 这一长串(token)拷下来**,等下贴到 `.env` 的 `CLOUDFLARED_TOKEN`。
6. 先不要点 Next。等容器跑起来后再回来配 hostname。

> Token 是长期凭据,**别提交到 git,别贴到任何公开地方**。
> 怀疑泄露:回这里 → Configure → Refresh token,旧 token 立即失效。

---

## 2. 在 Windows 本地准备配置文件

打开 PowerShell,`cd` 到项目根(假设 `E:\pythonproject\novel_auto`):

```powershell
cd E:\pythonproject\novel_auto

# 拷贝两个模板到项目根
copy deploy\docker\env.production.example .env
copy deploy\docker\config.production.example.json config.json
```

### 2.1 编辑 `.env`

```powershell
notepad .env
```

**必填**:

```
DEEPSEEK_API_KEY=sk-你真实的-deepseek-key
CLOUDFLARED_TOKEN=eyJhI...上面拷的整串token
```

可选:`LLM_PROVIDER` 换成 `mimo` / `custom` 并填对应那段。

### 2.2 编辑 `config.json`

```powershell
notepad config.json
```

**先用宽松 CORS 通起来,Vercel 上线后再收紧**:

```json
"server": {
  "host": "0.0.0.0",
  "backend_port": 8762,
  "frontend_port": 3143,
  "cors_origins": ["*"]
}
```

(`["*"]` 是临时态,正式上线必须改成具体 Vercel 域名 — 见 frontend/README.md)

---

## 3. 准备 data/ 目录(给 bind mount)

```powershell
mkdir data\backend
mkdir data\storage
mkdir data\hf_cache
```

这三个目录会被 mount 进容器:

| 宿主机 | 容器内 | 用途 |
|--------|--------|------|
| `data/backend` | `/app/backend/data` | tick_state / chroma / ticks.db / narratives |
| `data/storage` | `/app/data` | 顶层 data/(部分历史路径用到) |
| `data/hf_cache` | `/home/app/.cache` | sentence-transformers 模型缓存 |

> 这是**关键**:容器删了 / 镜像 rebuild 都不会丢业务数据。
> 备份只需 `7z a backup.7z data\` 一个目录。

---

## 4. 第一次 build & up

```powershell
docker compose -f deploy/docker/docker-compose.yml --env-file .env up -d --build
```

第一次会:
1. 拉 `python:3.11-slim-bookworm` 基础镜像(~120 MB)
2. 装 `build-essential / git / tini`(~300 MB)
3. `pip install -r requirements.txt` —— 下 torch / transformers / chromadb,**这步最慢**,几分钟到十几分钟
4. 拉 `cloudflare/cloudflared:latest`(~30 MB)
5. 启动两个容器

完事后 image 大概 **2.5~3 GB**,运行时 RAM **1.5~2 GB**。

### 4.1 看状态

```powershell
docker compose -f deploy/docker/docker-compose.yml ps
```

期望:

```
NAME                       STATUS                  PORTS
novel-auto-backend         Up X seconds (healthy)  127.0.0.1:8762->8762/tcp
novel-auto-cloudflared     Up X seconds
```

`healthy` 状态要等 backend 把 sentence-transformers 模型下载完(首次 ~150 MB,2~5 分钟),
在此之前 `health: starting`。

### 4.2 跟日志

```powershell
docker compose -f deploy/docker/docker-compose.yml logs -f
# Ctrl+C 退出 (不停服务)

# 只看后端
docker compose -f deploy/docker/docker-compose.yml logs -f backend

# 只看 cloudflared
docker compose -f deploy/docker/docker-compose.yml logs -f cloudflared
```

cloudflared 日志见到 `Registered tunnel connection` 一行(通常 4 个 connector,2 个 IPv4 / 2 个 IPv6)就是连上 CF 边缘了。

### 4.3 本地验证

```powershell
curl http://127.0.0.1:8762/api/health
# {"name":"AI 长篇小说生成 Agent 系统","version":"2.0.0","status":"running"}
```

通了 ✅ — 后端在 Windows 本地跑起来,Tunnel 也连上了 CF。

---

## 5. 在 Cloudflare 网页配 hostname

回到刚才那个 Tunnel 配置页面(or `Networks → Tunnels → 你的 tunnel → Configure → Public Hostname`):

1. **Add a public hostname**
2. 填:
   - **Subdomain**:`api.novel`(随便,但要记住)
   - **Domain**:你的 Cloudflare 域名,例如 `your-domain.com`
   - **Path**:留空
   - **Type**:`HTTP`
   - **URL**:`backend:8762`
     - ⚠️ 这里**不**填 `localhost:8762` 或 `127.0.0.1`。
     - `backend` 是 docker-compose.yml 里的 service name,
       同一 docker network 里 cloudflared 容器能直接解析到 backend 容器
3. **Additional application settings**(可选,SSE 友好):
   - Connection → Keep-alive timeout:`90s`
   - HTTP → Disable Chunked Encoding:**off**(保持开启,即 chunked 可用)
4. Save hostname

CF 会自动在 DNS 里建 CNAME `api.novel.your-domain.com → <tunnel-uuid>.cfargotunnel.com`,**不用** 手动改 DNS。

公网验证:

```powershell
curl https://api.novel.your-domain.com/api/health
# {"name":"AI 长篇小说生成 Agent 系统",...}
```

通了 ✅ — 公网入口就绪,可以拿这个 URL 去配 Vercel 前端的 `VITE_API_BASE`。

---

## 6. 日常运维

### 升级

```powershell
cd E:\pythonproject\novel_auto
git pull
docker compose -f deploy/docker/docker-compose.yml --env-file .env up -d --build
```

镜像层缓存会让 rebuild 只重做改动层,通常 1~3 分钟。

### 重启 / 停止 / 删除

```powershell
docker compose -f deploy/docker/docker-compose.yml restart backend          # 只重启后端
docker compose -f deploy/docker/docker-compose.yml stop                     # 停 (容器还在)
docker compose -f deploy/docker/docker-compose.yml down                     # 停 + 删容器 (data/ 不动)
docker compose -f deploy/docker/docker-compose.yml down --rmi local         # 连 image 也删
```

`down` 不会动 `data/` 下的 bind mount,放心删容器。

### 进容器排查

```powershell
docker exec -it novel-auto-backend bash
# 容器内:
ls /app/backend/data
python -c "from config.settings import settings; print(settings.deepseek_model)"
```

### 备份

```powershell
# 停服务保证 SQLite 一致性
docker compose -f deploy/docker/docker-compose.yml stop backend

# 压缩 data/ 目录
$ts = Get-Date -Format "yyyyMMdd-HHmm"
7z a "backup-$ts.7z" data\

# 恢复
docker compose -f deploy/docker/docker-compose.yml start backend
```

或者用 Docker Desktop 内置的 Volumes 视图也能直接看。

### 查 image 体积 / 清理

```powershell
docker images novel-auto-backend
docker system df            # 看 image / 容器 / volume / 构建缓存占多少
docker builder prune -af    # 清构建缓存 (rebuild 会重做, 但能省 ~5 GB)
```

---

## 7. 排错速查

| 现象 | 排查 |
|------|------|
| `docker compose up` 报 `Cannot connect to the Docker daemon` | Docker Desktop 没启动,任务栏托盘看下 |
| build 卡在 `Installing sentence-transformers` | torch 下载慢,等;真过分了换镜像源:`pip install ... -i https://pypi.tuna.tsinghua.edu.cn/simple`,在 Dockerfile 加 `--index-url` |
| 启动后 `health: starting` 一直不变 | `docker compose logs backend` 看是不是 sentence-transformers 还在下模型 (~150 MB) |
| `health: unhealthy` | `docker exec novel-auto-backend python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8762/api/health').read())"` 看真错 |
| cloudflared 日志 `Tunnel credentials are invalid` | `CLOUDFLARED_TOKEN` 复制错(漏字符 / 多空格),重抄 |
| cloudflared 日志 `connection refused` | backend healthcheck 没过,cloudflared 在等;先让 backend healthy |
| 网页配 hostname 后公网 502 | `URL` 写成了 `localhost:8762` 而不是 `backend:8762`;改成 `backend:8762` 立刻生效,不用重启 |
| Vercel 调 API 报 CORS | `config.json` 的 `cors_origins` 没加 Vercel 域名;改完 `docker compose restart backend`(config.json 是 ro mount,改宿主机文件容器立即看到新内容,但 `settings` 是模块加载期快照,要 restart) |
| Windows 路径里有空格 | docker-compose bind mount 用相对路径(`../..`)就行,避开绝对路径里的空格 |
| 容器拉镜像慢 | Docker Desktop → Settings → Docker Engine,加 `"registry-mirrors": ["https://docker.mirrors.ustc.edu.cn"]` |

---

## 8. 安全提醒

- ✅ 后端只 bind `127.0.0.1:8762`(compose 已经这么写),不在公网 8762
- ✅ Cloudflared token 走 `.env`,**已经在** `.gitignore` 里
- ✅ 容器内用非 root 用户 `app`(uid 1001)
- ✅ `config.json` 用 `:ro` 挂载,容器内代码不能写
- ⚠️ `.env` 里有真凭据,别 `git add` — 项目根 `.gitignore` 已把 `.env` 排除
- ⚠️ 如果用 Docker Desktop 的 WSL2 backend,`data/` 实际落在 WSL2 虚拟磁盘,
  Windows 资源管理器看不到完整路径(可在地址栏输 `\\wsl.localhost\` 进入)。
  bind mount 写到 Windows 盘符路径(`E:\...`)也支持,但 I/O 性能差 ~3 倍。
  推荐让 `data/` 留在 Windows 盘符上(项目根),性能够用,备份方便。

## 9. 不需要的就别开

cloudflared 容器跑起来就在产生流量(心跳 + DNS 注册)。如果暂时不想公网暴露,
单独停掉它即可:

```powershell
docker compose -f deploy/docker/docker-compose.yml stop cloudflared
# 后端仍在 127.0.0.1:8762, 本地浏览器照常访问
```
