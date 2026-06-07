# syntax=docker/dockerfile:1.6
# ============================================================
# 无限小说生成系统 — 后端镜像
# 基础:debian-slim + python 3.11
# 跨平台:linux/amd64 + linux/arm64 (Apple Silicon / Windows ARM)
# ============================================================
FROM python:3.11-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/app/.cache/sentence_transformers

# tini 作 PID1 处理信号; 其余是 sentence-transformers / chromadb 编译需要的工具链
# (rust/cargo 给 tokenizers, gcc 给 chroma 的本地扩展)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        build-essential \
        gcc g++ \
        git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# 非 root 用户 (uid 1001 避开 Docker Desktop on Windows 的 root 默认)
# ------------------------------------------------------------
RUN useradd --uid 1001 --user-group --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# ------------------------------------------------------------
# 依赖层 — 单独 COPY requirements 走 BuildKit 缓存
# ------------------------------------------------------------
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip wheel \
    && pip install -r /app/requirements.txt

# ------------------------------------------------------------
# 项目代码 — .dockerignore 已经把 data/ / .venv / .git / old / node_modules 排掉
# ------------------------------------------------------------
COPY --chown=app:app . /app

# 容器内创建运行期写目录, 提前 chown — 否则首次写 bind mount 时权限会拧巴
RUN mkdir -p /app/backend/data /app/data /home/app/.cache \
    && chown -R app:app /app/backend/data /app/data /home/app/.cache

USER app

EXPOSE 8762

# 容器内健康检查 — uvicorn 起来后 /api/health 应即返回 200。
# start-period 120s 留给 sentence-transformers 首次下载模型 (~150 MB)。
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8762/api/health', timeout=5).status==200 else 1)"

# tini 转发 SIGTERM 给 uvicorn → 触发 FastAPI shutdown 钩子 (关 TickDB)
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-u", "run.py", "--host", "0.0.0.0", "--port", "8762"]
