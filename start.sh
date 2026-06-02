#!/usr/bin/env bash
# 启动后端 + 前端 dev 服务器
# 后端: http://127.0.0.1:8000  前端: http://127.0.0.1:3000/nw/

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

python run.py --reload &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" INT TERM EXIT

echo
echo "Backend  PID=$BACKEND_PID  → http://127.0.0.1:8000"
echo "Frontend PID=$FRONTEND_PID  → http://127.0.0.1:3000/nw/"
echo
wait
