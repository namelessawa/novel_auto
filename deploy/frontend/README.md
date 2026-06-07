# 前端部署 — Vercel

> 把 `frontend/` 单独部署到 Vercel,API 通过 `VITE_API_BASE` 指向 Cloudflare Tunnel
> 的 hostname。后端 CORS 显式放行 Vercel 域名。

## 一句话

1. Vercel 控制台 → New Project → Import 这个仓库
2. **Root Directory** 选 `frontend`
3. Environment Variables 加 `VITE_API_BASE` 和 `VITE_BASE_PATH=/`
4. Deploy

完事。下面是细节。

---

## 1. 项目设置(Vercel 控制台)

新建 Project,关键项:

| 字段 | 值 |
|------|-----|
| Framework Preset | **Vite**(Vercel 一般会自动识别) |
| **Root Directory** | **`frontend`** ← 必须改,默认会指仓库根 |
| Build Command | `npm run build`(已在 vercel.json) |
| Output Directory | `dist`(已在 vercel.json) |
| Install Command | `npm install`(已在 vercel.json) |
| Node.js Version | 20.x(默认即可) |

`vercel.json`(放在 `frontend/` 下,见 [`./vercel.json`](./vercel.json))会自动:
- SPA fallback:任何 path → `index.html`
- 长期缓存 `/assets/*`
- 加 `X-Frame-Options`、`Referrer-Policy` 等安全头

## 2. 环境变量

在 Vercel 项目 → Settings → Environment Variables 加这两个(三个环境都加:Production / Preview / Development):

```
VITE_API_BASE=https://api.novel.your-domain.com
VITE_BASE_PATH=/
```

**`VITE_API_BASE` 取值**:
- 你在 [`../cloudflared/`](../cloudflared/) 里绑的 hostname,不带末尾斜杠
- 不带 `/api` 后缀(代码里 `services/api.js` 自己拼)

**`VITE_BASE_PATH=/`**:
- 项目自带 `base: '/nw/'` 是给同源部署用的(FastAPI mount 到 `/nw/`)
- Vercel 走根路径,必须显式覆盖为 `/`
- `vite.config.js` 已支持读这个 env

## 3. 部署

```bash
# 命令行(可选)
npm i -g vercel
cd frontend
vercel link
vercel env pull .env.production.local     # 拉环境变量到本地
vercel --prod                              # 推生产
```

或者在 Vercel 控制台点 Deploy。每次 `git push` 到 main 都会自动部署。

## 4. 自定义域名

Vercel → Project → Settings → Domains → Add Domain:
- 添加 `novel.your-domain.com`
- 按提示在 Cloudflare DNS 加 CNAME → `cname.vercel-dns.com`
- 等几分钟自动签 SSL

加完后把这个域名也加到后端 `config.json` 的 `cors_origins`,重启后端:

```json
"cors_origins": [
  "https://novel.your-domain.com",
  "https://novel-frontend.vercel.app"
]
```

## 5. Preview Deployment(可选)

每个 PR / 分支 Vercel 会自动起一个 preview URL,形如
`novel-frontend-git-fix-abc-xxx.vercel.app`。

想让 preview 也能调后端,有两种方案:

### 方案 A:CORS 通配(简单)

在后端 `backend/main.py` 改 CORSMiddleware:

```python
import re
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://novel-frontend(-git-.*)?\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 方案 B:Preview 走独立后端

让 preview branch 指向 staging 后端(staging Cloudflare Tunnel 走另一个 hostname)。
Vercel 支持按环境分配不同 `VITE_API_BASE`:Settings → Environment Variables →
对每个变量勾 Production / Preview / Development 分别填值。

## 6. 流式接口(SSE)注意

前端 `/api/generate/stream` 是 SSE。在 Vercel 这里没问题,因为:
- Vercel 只托管静态资源,不代理 API
- SSE 直连 Cloudflare Tunnel → 服务器,Vercel 不在链路上

所以无需在 `vercel.json` 给 API 路由特殊配置。

## 7. 排错速查

| 现象 | 排查 |
|------|------|
| 部署成功但页面白屏,Network 全 404 `/nw/assets/...` | `VITE_BASE_PATH` 没设 `/`,redeploy |
| 页面正常但 API 全 CORS 错 | 后端 `config.json.cors_origins` 没加 Vercel 域名,改了要重启后端 |
| `Failed to fetch` | `VITE_API_BASE` 拼错(多了 `/api` 后缀,或末尾斜杠) |
| 部署 build 失败 `Cannot find module 'react'` | Root Directory 没选 `frontend`,Vercel 在仓库根跑 npm install 找不到 |
| 看不到环境变量 | 加完变量必须重新 deploy 才生效(redeploy 当前 commit) |
| Preview URL 504 | 后端 cloudflared 没起 / DNS 没指向 tunnel |
| 自定义域名 CNAME 添加后 vercel 还说 invalid | 等 5~30 分钟,或在 Cloudflare 关掉这条 CNAME 的橙色云(改成 DNS only) |

## 8. 为什么前端不和后端走同源 `/api`

如果想前后端同源(`https://novel.your-domain.com` 同时承载 SPA 和 API),
需要 Vercel 用 `rewrites` 把 `/api/*` 反代到后端:

```json
{
  "rewrites": [
    {
      "source": "/api/(.*)",
      "destination": "https://api.novel.your-domain.com/api/$1"
    }
  ]
}
```

⚠️ 这种做法**不推荐**,因为:
- Vercel rewrite 不支持 SSE 长连接(超时 10s ~ 30s)
- 多一跳,延迟增加
- `/api/generate/stream` 会直接断

**推荐架构**(默认):前端 `novel.x.com`(Vercel)+ 后端 `api.novel.x.com`(CF Tunnel),
跨域走 CORS。代码已经是这个形态。
