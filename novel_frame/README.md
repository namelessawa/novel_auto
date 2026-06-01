# AI Novel Agent - 长篇小说生成系统

多模块协同的 Agent 架构，以 LLM 为推理核心，外挂分层记忆引擎与动态状态机，实现百万字级逻辑连贯的长篇小说生成。

## 目录

- [本地开发](#本地开发)
- [生产部署](#生产部署)
  - [一、后端部署（Linux 服务器）](#一后端部署linux-服务器)
  - [二、前端部署（Vercel）](#二前端部署vercel)
  - [三、联调验证](#三联调验证)
- [架构说明](#架构说明)
- [API 参考](#api-参考)
- [故障排查](#故障排查)

---

## 本地开发

```bash
# 1. 配置
cp config.example.json config.json
# 编辑 config.json，填入 DeepSeek API Key

# 2. 一键启动（Windows）
start.bat

# 2. 一键启动（Linux/macOS）
chmod +x start.sh && ./start.sh
```

自动完成：创建 Python venv → 安装后端依赖 → 安装前端依赖 → 启动双服务 → 打开浏览器。

---

## 生产部署

### 架构总览

```
用户浏览器
    │
    │  https://your-domain.com/nw/*
    ▼
┌─────────┐     SPA 静态资源       ┌───────────────┐
│  Vercel │◄────────────────────── │ frontend/dist  │
└────┬────┘                        └───────────────┘
     │
     │  https://your-server.com/api/*
     ▼
┌─────────┐     反向代理          ┌──────────────────┐
│  Nginx  │ ──────────────────► │ uvicorn :8000     │
└─────────┘                      │ (novel-agent.svc) │
                                 └──────────────────┘
```

---

### 一、后端部署（Linux 服务器）

以下示例中使用 `<PROJECT>` 表示你在服务器上存放项目的实际路径（如 `/home/user/apps/novel-agent`），请替换为你的真实路径。

#### 1.1 环境要求

| 依赖 | 版本 |
|------|------|
| Python | >= 3.11 |
| pip | >= 23.0 |
| Nginx | >= 1.18 |
| systemd | 已预装 |

#### 1.2 上传项目文件

在**本地**执行，将后端代码和配置上传到服务器上你选择的目录：

```bash
# 上传后端代码（排除本地运行时产物）
rsync -avz --exclude .venv --exclude data --exclude __pycache__ \
  ./backend/ user@your-server:<PROJECT>/backend/

# 上传根目录配置文件
scp config.example.json user@your-server:<PROJECT>/config.example.json

# 上传 systemd 服务文件模板
scp deploy/novel-agent.service user@your-server:<PROJECT>/novel-agent.service
```

#### 1.3 服务器上安装

SSH 登录服务器后执行：

```bash
cd <PROJECT>

# 复制并编辑配置文件
cp config.example.json config.json
nano config.json
# 填入你的 DeepSeek API Key 和 cors_origins
```

`config.json` 关键配置：

```json
{
  "llm": {
    "api_key": "sk-your-actual-deepseek-key",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat"
  },
  "server": {
    "host": "0.0.0.0",
    "backend_port": 8000,
    "cors_origins": [
      "https://your-domain.com",
      "https://your-project.vercel.app"
    ]
  }
}
```

> **重要**：`cors_origins` 必须填写你的 Vercel 前端域名，否则浏览器会拦截跨域请求。

```bash
# 创建虚拟环境并安装依赖
cd <PROJECT>/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 创建数据目录
mkdir -p data/chroma data/snapshots

# 验证能否正常启动
python main.py
# 看到 Uvicorn running 后 Ctrl+C 退出
```

#### 1.4 配置 systemd 服务

编辑 service 文件，**将路径替换为你的实际路径**：

```bash
nano <PROJECT>/novel-agent.service
```

需要修改的三处（已在文件中用注释标出）：

```ini
WorkingDirectory=<PROJECT>/backend
ExecStart=<PROJECT>/backend/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
ReadWritePaths=<PROJECT>/backend/data
```

如果运行用户不是 `www-data`，同时修改 `User=` 和 `Group=`。

安装并启动服务：

```bash
# 复制到 systemd 目录
sudo cp <PROJECT>/novel-agent.service /etc/systemd/system/novel-agent.service

# 设置配置文件权限（保护 API Key）
sudo chmod 600 <PROJECT>/config.json

# 加载、启用、启动
sudo systemctl daemon-reload
sudo systemctl enable novel-agent
sudo systemctl start novel-agent

# 确认状态
sudo systemctl status novel-agent
```

#### 1.5 systemctl 常用命令

```bash
sudo systemctl status novel-agent          # 查看状态
sudo journalctl -u novel-agent -f          # 实时日志
sudo systemctl restart novel-agent         # 重启（改配置后）
sudo systemctl stop novel-agent            # 停止
sudo systemctl disable novel-agent         # 禁用开机自启
```

#### 1.6 配置 Nginx 反向代理

在 Nginx 已有的 `server {}` 块中添加以下 `location`：

```nginx
# /etc/nginx/sites-available/your-site.conf

server {
    listen 443 ssl;
    server_name your-server.com;

    # ...existing SSL and other config...

    # Novel Agent Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE streaming support（必须关闭缓冲）
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        chunked_transfer_encoding off;

        # LLM 生成需要较长超时
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

```bash
sudo nginx -t                  # 测试配置
sudo systemctl reload nginx    # 重载
```

#### 1.7 验证后端

```bash
# 直连测试
curl http://localhost:8000/
# 应返回: {"name":"AI 长篇小说生成 Agent 系统","version":"1.0.0","status":"running"}

# 通过 Nginx 测试
curl https://your-server.com/api/stats
# 应返回 JSON 统计信息
```

---

### 二、前端部署（Vercel）

#### 2.1 配置后端地址

编辑 `frontend/.env.production`，设置后端服务器地址：

```env
VITE_API_BASE=https://your-server.com
```

或在 Vercel Dashboard → Settings → Environment Variables 中添加：

| Name | Value |
|------|-------|
| `VITE_API_BASE` | `https://your-server.com` |

#### 2.2 部署方式一：Vercel CLI

```bash
cd frontend
npm i -g vercel    # 首次安装 CLI
vercel --prod      # 部署
```

#### 2.3 部署方式二：Git 集成

1. 将代码推送到 GitHub/GitLab
2. 在 [Vercel Dashboard](https://vercel.com/new) 导入仓库
3. 配置：
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. 添加环境变量 `VITE_API_BASE`
5. 点击 Deploy

#### 2.4 主域名 Rewrites 配置

前端部署在子路径 `/nw` 下。`frontend/vercel.json` 已包含本项目的 SPA rewrites。

如果 `/nw` 的 rewrites 配置在**主域名项目**（非本项目）中，则在主域名的 `vercel.json` 添加：

```json
{
  "rewrites": [
    {
      "source": "/nw",
      "destination": "https://your-novel-project.vercel.app/nw"
    },
    {
      "source": "/nw/:match*",
      "destination": "https://your-novel-project.vercel.app/nw/:match*"
    }
  ]
}
```

将 `your-novel-project.vercel.app` 替换为本项目在 Vercel 上的实际域名。

#### 2.5 验证前端

访问 `https://your-domain.com/nw`，应看到 AI Novel Agent 界面。

---

### 三、联调验证

#### 3.1 检查清单

| 检查项 | 命令/方法 | 预期结果 |
|--------|----------|---------|
| 后端运行中 | `systemctl status novel-agent` | active (running) |
| 后端 API 可达 | `curl https://your-server.com/api/stats` | 返回 JSON |
| 前端加载 | 访问 `https://your-domain.com/nw` | 页面正常渲染 |
| 前端连后端 | 页面顶栏显示统计数据 | 章节/字数/实体数显示正常 |
| SSE 流式生成 | 点击"生成下一节" | Pipeline 状态更新 + 文字流式输出 |
| CORS 正确 | 浏览器 DevTools Network | 无 CORS 错误 |

#### 3.2 常见问题

**CORS 错误**

浏览器控制台出现 `Access-Control-Allow-Origin` 错误：
- 检查 `config.json` 中 `server.cors_origins` 是否包含前端域名
- 重启后端：`sudo systemctl restart novel-agent`

**SSE 流式输出中断**

Nginx 默认会缓冲代理响应，导致 SSE 事件不实时推送：
- 确保 Nginx 配置中 `/api/` 的 `proxy_buffering off;` 已生效
- 确保 `proxy_read_timeout` 足够长（建议 300s）

**502 Bad Gateway**

- 检查后端是否运行中：`systemctl status novel-agent`
- 检查端口是否匹配：Nginx `proxy_pass` 端口 = `config.json` 中 `backend_port`
- 查看日志：`journalctl -u novel-agent -n 50`

**前端页面空白**

- 确认 Vercel 环境变量 `VITE_API_BASE` 已正确设置
- 确认 Vercel rewrites 规则指向 `/nw/index.html`
- 检查浏览器控制台是否有 JS 加载 404

---

## 架构说明

### 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 工作记忆 | `memory/working_memory.py` | 环形队列，维持最近 2-3 节上下文 |
| 动态摘要树 | `memory/summary_tree.py` | N 叉树分层压缩，提供全局大纲 |
| 知识图谱 | `graph/knowledge_graph.py` | NetworkX 有向图，实体/关系管理 + 快照回滚 |
| 向量检索 | `vector/vector_store.py` | ChromaDB，语义相似度召回历史伏笔 |

### Agent 协作管线

```
Context 组装 → 意图规划 → 信息检索 → 逻辑审查 → 正文生成 → 状态同步
                 ↑                        │
                 └── 冲突？重新规划 ◄──────┘
```

---

## API 参考

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/generate` | 生成下一节（同步） |
| POST | `/api/generate/stream` | 生成下一节（SSE 流式） |
| POST | `/api/chapter/advance` | 进入下一章 |
| POST | `/api/rollback` | 回滚到指定章节 |
| GET | `/api/stats` | 系统统计信息 |
| GET | `/api/sections` | 所有已生成章节 |
| GET | `/api/text` | 全文导出 |
| GET | `/api/graph` | 知识图谱数据 |
| GET/POST | `/api/graph/entities` | 实体管理 |
| GET/POST | `/api/graph/relations` | 关系管理 |
| GET | `/api/outline` | 摘要树大纲 |
| GET | `/api/memory` | 工作记忆状态 |
| GET/POST | `/api/snapshots` | 快照管理 |
| POST | `/api/reset` | 重置 Pipeline |

---

## 故障排查

```bash
# 后端日志
sudo journalctl -u novel-agent -f

# 后端手动启动（调试模式）
cd <PROJECT>/backend
source .venv/bin/activate
python main.py

# Nginx 日志
sudo tail -f /var/log/nginx/error.log

# 测试 DeepSeek API 连通性
curl -s https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```
