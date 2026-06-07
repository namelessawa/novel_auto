# 后端部署 — Linux + systemd

> 把 FastAPI tick 后端跑成一个 systemd 服务,仅监听 `127.0.0.1:8762`,
> 由 [`../cloudflared/`](../cloudflared/) 内的 Cloudflare Tunnel 把它通到公网。

## 一句话

```bash
sudo git clone <repo> /opt/novel_auto
sudo bash /opt/novel_auto/deploy/backend/install.sh
sudo -e /opt/novel_auto/.env             # 填 DEEPSEEK_API_KEY
sudo -e /opt/novel_auto/config.json      # 改 cors_origins
sudo systemctl start novel-agent
curl http://127.0.0.1:8762/api/health
```

---

## 1. 服务器准备

- OS:Debian 12 / Ubuntu 22.04+ / RHEL/Rocky 9+
- 配置:**建议 ≥ 2 vCPU / 4 GB RAM / 30 GB SSD**
  - chromadb + sentence-transformers 启动会占 1~1.5 GB
  - 9 Agent 并发跑 deepseek 时 CPU 间歇打满,RAM 稳态约 1.5~2.5 GB
- 出网:能访问 `api.deepseek.com` (或你的 LLM provider)
- 入站端口:**不需要开!** Cloudflare Tunnel 走出站,8762 只 bind `127.0.0.1`
- 用户:推荐用专用账号 `novel`(`install.sh` 会自动建)

## 2. 安装

### 2.1 自动脚本(推荐)

```bash
sudo git clone https://github.com/your-org/novel_auto.git /opt/novel_auto
sudo bash /opt/novel_auto/deploy/backend/install.sh
```

可调环境变量:

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `INSTALL_DIR` | `/opt/novel_auto` | 项目根目录 |
| `SERVICE_USER` | `novel` | 服务运行账号 |
| `PYTHON_BIN` | `python3.11` | Python 解释器(项目要求 3.10+) |
| `NOVEL_REPO` | 空 | 非空时由脚本 `git clone` |

脚本会:
1. 装 `git curl python3.11 python3.11-venv build-essential`
2. 建无 shell 服务账号 `novel`
3. 建 venv 并 `pip install -r requirements.txt`
4. 拷贝 `.env` / `config.json` 模板
5. 安装 systemd unit 并 `enable`
6. **不会** 启动服务 — 留时间让你填 API Key

### 2.2 手动安装(如果你想自己控制)

```bash
# 1. 装依赖
sudo apt update && sudo apt install -y git python3.11 python3.11-venv build-essential

# 2. 建账号
sudo useradd -r -s /usr/sbin/nologin -d /opt/novel_auto novel

# 3. 拉代码
sudo git clone https://github.com/your-org/novel_auto.git /opt/novel_auto
sudo chown -R novel:novel /opt/novel_auto

# 4. venv
sudo -u novel python3.11 -m venv /opt/novel_auto/.venv
sudo -u novel /opt/novel_auto/.venv/bin/pip install -r /opt/novel_auto/requirements.txt

# 5. 配置
sudo cp /opt/novel_auto/deploy/backend/env.production.example /opt/novel_auto/.env
sudo cp /opt/novel_auto/deploy/backend/config.production.example.json /opt/novel_auto/config.json
sudo chown novel:novel /opt/novel_auto/.env /opt/novel_auto/config.json
sudo chmod 600 /opt/novel_auto/.env
sudo -e /opt/novel_auto/.env             # 填 API Key
sudo -e /opt/novel_auto/config.json      # 改 cors_origins

# 6. systemd
sudo cp /opt/novel_auto/deploy/backend/novel-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now novel-agent
```

## 3. 配置详解

### 3.1 `.env`(`/opt/novel_auto/.env`,权限 600)

模板见 [`env.production.example`](./env.production.example)。**生产关键项**:

```bash
AGENT_HOST=127.0.0.1     # 务必 127.0.0.1, 别填 0.0.0.0
AGENT_PORT=8762
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
```

### 3.2 `config.json`(`/opt/novel_auto/config.json`)

模板见 [`config.production.example.json`](./config.production.example.json)。
**最重要的一项是 CORS**:

```json
"server": {
  "host": "127.0.0.1",
  "backend_port": 8762,
  "cors_origins": [
    "https://novel.your-domain.com",
    "https://novel-frontend.vercel.app"
  ]
}
```

> `cors_origins` 留 `["*"]` 是危险的 — 暴露后任何站点 JS 都能调你的 API。
> 必须显式列出 Vercel 域名(含自定义域名 + `*.vercel.app` 预览域名,
> 如要支持 preview deployment,详见 [`../frontend/README.md`](../frontend/README.md))。

### 3.3 `llm.api_key` 在 `config.json` vs `.env` 怎么选

代码里 [`backend/config/settings.py`](../../backend/config/settings.py) 的优先级:

1. **`config.json.llm.api_key` 非空** → 用 config.json 整段
2. 否则用 `.env` 的 `LLM_PROVIDER` + 对应 provider 的凭据
3. 都空 → API 调用会显式报错

**推荐**:`config.json` 留空 `api_key`,让 `.env` 接管 — 这样:
- 切 provider 只改 `.env` 的 `LLM_PROVIDER=mimo` 一行就行,不用动 config.json
- UI 上 `PUT /api/config/llm` 会把 key 写进 config.json,但生产建议把这个端点禁掉
  或挡在内网

## 4. 服务管理

```bash
sudo systemctl start    novel-agent       # 启动
sudo systemctl stop     novel-agent       # 停止
sudo systemctl restart  novel-agent       # 重启
sudo systemctl status   novel-agent       # 看状态
sudo systemctl enable   novel-agent       # 开机自启
sudo systemctl disable  novel-agent       # 关开机自启
journalctl -u novel-agent -f              # 实时看日志
journalctl -u novel-agent --since '1h ago' # 最近 1 小时
```

启动后**等 10~30 秒**(chromadb + sentence-transformers 首次加载慢),然后:

```bash
curl http://127.0.0.1:8762/api/health
# {"name":"AI 长篇小说生成 Agent 系统","version":"2.0.0","status":"running"}
```

## 5. 升级

```bash
sudo bash /opt/novel_auto/deploy/backend/update.sh
# 等价于: git pull --ff-only + (requirements.txt 改了就 pip install) + systemctl restart + 健康检查
```

可调:

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `BRANCH` | `main` | 切到哪个分支 |
| `SKIP_PIP` | `0` | 跳过 pip 升级(只想重启时) |
| `NO_RESTART` | `0` | 只更新代码不重启 |

## 6. 备份

```bash
# 手动
sudo bash /opt/novel_auto/deploy/backend/backup.sh

# 加 cron(每天凌晨 4 点)
echo "0 4 * * * root /opt/novel_auto/deploy/backend/backup.sh" \
  | sudo tee /etc/cron.d/novel-agent-backup
```

备份产物落到 `/var/backups/novel-agent/novel-data-YYYYMMDD-HHMM.tar.zst`,
默认留 14 天(`KEEP_DAYS=`)。装了 `zstd` 就用 zstd,否则回落到 gz。

**注意**:`ticks.db` 是 SQLite WAL,备份时如果服务正在写,可能拿到不一致快照。
真要严谨,前置 `systemctl stop` 一下再备份。我们的备份策略偏向"灾难恢复够用"。

## 7. 排错速查

| 现象 | 排查 |
|------|------|
| `systemctl status` 显示 `Active: failed` | `journalctl -u novel-agent -n 100` 看 traceback |
| 报 `FileNotFoundError: config.json` | 拷模板:`cp deploy/backend/config.production.example.json /opt/novel_auto/config.json` |
| 启动后卡 30s 才能 curl | 正常,sentence-transformers 首次下载模型 |
| `curl /api/health` 通,但 Vercel 报 CORS 错 | `config.json` 的 `cors_origins` 没加 Vercel 域名 |
| 报 `Address already in use` | `ss -ltnp | grep 8762` 查谁占了,或改 `.env` 的 `AGENT_PORT` |
| chroma 报 `sqlite3 < 3.35` | RHEL 系老内核要装 `pysqlite3-binary` 或升级 |
| 日志疯狂刷 200 OK | 看 `backend/main.py` 已经做了 access log filter,只是没过滤 4xx/5xx,正常 |
| `pip install sentence-transformers` 卡死 | torch 下载慢,加 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple` |

## 8. 安全建议

- ✅ **绝不**把 8762 暴露公网,用 Cloudflare Tunnel(或 nginx + Let's Encrypt + Token 验证)
- ✅ `.env` 权限 `600`,`config.json` 权限 `644`
- ✅ systemd unit 已开 `NoNewPrivileges`/`ProtectSystem=strict`/`PrivateTmp` 等沙箱
- ✅ 服务账号 `novel` 用 `/usr/sbin/nologin` shell
- ⚠️ `PUT /api/config/llm` 端点能改 API Key,生产建议:
  - 选项 A:把这个路由从 `backend/api/routes.py` 删掉
  - 选项 B:Cloudflare Access 套一层 SSO
- ⚠️ 备份目录 `/var/backups/novel-agent` 也含 chroma/snapshot,权限收紧(`chmod 700`)

## 9. 反向代理替代方案

如果不走 Cloudflare Tunnel,而是直接 VPS 上挂域名:见仓库根的旧 `deploy/nginx-novel-agent.conf`
(已迁移到 [`./nginx-novel-agent.conf`](./nginx-novel-agent.conf))。
注意要自己搞 HTTPS(Caddy / Let's Encrypt)和速率限制。
