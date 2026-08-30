"""v2.48 验收 — 跑过 Sprint 1/2 改动用到的全部 API 端点。

Tier 1 (本脚本): 结构性 smoke — 每个端点 200 或预期错误码 即 PASS.
Tier 2 (后续): 用 coding.txt 跑真实 LLM 链路 (bootstrap + 首节 + tick advance).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

import requests

BASE = "http://127.0.0.1:8762"

# 不走系统代理 — http_proxy=127.0.0.1:7897 会把本地 loopback 也劫持掉
PROXIES = {"http": "", "https": ""}


def mint_token() -> str:
    out = subprocess.check_output(
        [sys.executable, "smoke_mint_token.py"],
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    return out.decode().strip().splitlines()[-1]


TOKEN = mint_token()
HDR = {"Authorization": f"Bearer {TOKEN}"}


def call(method: str, path: str, body: dict | None = None, expect=(200, 201)) -> tuple[bool, Any]:
    url = BASE + path
    try:
        if method == "GET":
            r = requests.get(url, headers=HDR, proxies=PROXIES, timeout=10)
        elif method == "POST":
            r = requests.post(url, headers=HDR, json=body or {}, proxies=PROXIES, timeout=10)
        elif method == "DELETE":
            r = requests.delete(url, headers=HDR, proxies=PROXIES, timeout=10)
        else:
            return False, f"unknown method {method}"
    except Exception as e:
        return False, f"network err {e}"
    ok = r.status_code in expect
    try:
        body_out = r.json()
    except Exception:
        body_out = r.text[:200]
    return ok, {"status": r.status_code, "body": body_out}


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


passes = 0
fails: list[str] = []


def check(name: str, method: str, path: str, body=None, expect=(200, 201)) -> Any:
    global passes
    ok, res = call(method, path, body, expect)
    status = res["status"] if isinstance(res, dict) else "?"
    if ok:
        passes += 1
        print(f"  PASS  {method:6s} {path:48s} {status}")
        return res.get("body") if isinstance(res, dict) else None
    else:
        fails.append(f"{method} {path} → {status}")
        body_short = json.dumps(res.get("body", res))[:120] if isinstance(res, dict) else str(res)[:120]
        print(f"  FAIL  {method:6s} {path:48s} {status}  {body_short}")
        return None


# ── P0-2: preset matrix
banner("P0-2 preset matrix")
pr = check("PRESETS", "GET", "/api/presets")
if isinstance(pr, dict):
    print(f"        themes={len(pr.get('themes', []))} styles={len(pr.get('styles', []))} "
          f"rec.available={pr.get('recommendations', {}).get('available')}")

# ── 必须先有 novel
banner("setup: 建一个测试 novel")
nv = check("CREATE_NOVEL", "POST", "/api/novels", {"title": "smoke_v248"}, expect=(200, 201))
novel_id = nv.get("id") if isinstance(nv, dict) else None
print(f"        novel_id={novel_id}")
if novel_id:
    check("SWITCH", "POST", f"/api/novels/{novel_id}/switch")

# ── P0-1: 续写
banner("P0-1 续写任务入队")
# 没 bootstrap 时后端可能 409/400 — 也算 wiring 通
check("SECTION_GEN", "POST", "/api/section/generate", {"novel_id": novel_id}, expect=(200, 201, 400, 409))

# ── P0-3 + P1-2 (loops) + reader (P1-3): tick state + 6 诊断端点
banner("P0-3 Tick + Diagnostics")
check("TICK_STATUS", "GET", "/api/tick/status")
check("TICK_HISTORY", "GET", "/api/tick/history?last_n=20")
check("HALLUCINATION", "GET", "/api/tick/diagnostic/hallucination")
check("CHAR_STATES", "GET", "/api/tick/character-states")
check("EVENT_STATS", "GET", "/api/tick/event-stats?last_n_ticks=50")
check("ACTION_PATTERNS", "GET", "/api/tick/action-patterns?last_n_ticks=100")
check("NOVELTY", "GET", "/api/tick/novelty-warnings")
check("STYLE_ANCHORS", "GET", "/api/tick/style-anchors?top_k=20")

# ── P1-2: OpenLoop CRUD
banner("P1-2 OpenLoop CRUD")
loops = check("LOOPS_LIST", "GET", "/api/tick/open-loops?top_k=20")
add_res = check(
    "LOOP_ADD",
    "POST",
    "/api/tick/open-loops",
    {
        "id": "smoke_loop_001",
        "description": "smoke-test 伏笔",
        "urgency": 7,
        "involved_characters": [],
        "opened_tick": 1,
    },
    expect=(200, 201, 409),
)
check("LOOP_LIST_2", "GET", "/api/tick/open-loops?top_k=20")
check("LOOP_DEL", "DELETE", "/api/tick/open-loops/smoke_loop_001", expect=(200, 204, 404))

# ── P1-4: inject event
banner("P1-4 InjectEvent (完整字段)")
check(
    "INJECT_EVT",
    "POST",
    "/api/tick/inject-event",
    {
        "type": "dramatic",
        "id": "smoke_evt_001",
        "location": "smoke_market",
        "participants": [],
        "description": "smoke 测试: 注入事件全字段",
        "narrative_value": 7,
        "visible_to": ["all"],
    },
    expect=(200, 201),
)

# ── P1-1: KG CRUD
banner("P1-1 KG CRUD")
check("GRAPH", "GET", "/api/graph")
ent = check(
    "ENTITY_ADD",
    "POST",
    "/api/graph/entities",
    {
        "id": "smoke_ent_001",
        "name": "测试角色",
        "entity_type": "character",
        "attributes": {"role": "smoke"},
    },
    expect=(200, 201, 409),
)
ent2 = check(
    "ENTITY_ADD_2",
    "POST",
    "/api/graph/entities",
    {
        "id": "smoke_ent_002",
        "name": "测试地点",
        "entity_type": "location",
        "attributes": {},
    },
    expect=(200, 201, 409),
)
check(
    "REL_ADD",
    "POST",
    "/api/graph/relations",
    {
        "source_id": "smoke_ent_001",
        "target_id": "smoke_ent_002",
        "relation_type": "located_at",
        "label": "smoke 关系",
    },
    expect=(200, 201, 409),
)
check("REL_DEL", "DELETE", "/api/graph/relations?source_id=smoke_ent_001&target_id=smoke_ent_002", expect=(200, 204, 404))
check("ENT_DEL_1", "DELETE", "/api/graph/entities/smoke_ent_001", expect=(200, 204, 404))
check("ENT_DEL_2", "DELETE", "/api/graph/entities/smoke_ent_002", expect=(200, 204, 404))

# ── P0-4 multimodal: list + manifest (无 LLM 只看 wiring)
banner("P0-4 Multimodal (list 端点)")
check("MM_VOICES", "GET", "/api/multimodal/voices")
check("MM_SECTIONS", "GET", f"/api/multimodal/{novel_id}/list")

# ── Reader (P1-3) — same endpoints as above + narratives
banner("P1-3 Reader 侧栏端点")
check("NARRATIVES", "GET", "/api/tick/narratives?limit=5")
check("LOOPS_READER", "GET", "/api/tick/open-loops?top_k=50")
# CharStates 已经在 P0-3 测过

# ── 清理 + 总结
banner("cleanup")
if novel_id:
    # 必须先切走才能删 — 后端 400: "不能删除当前活跃的小说"
    # 没有第二个 novel 可切, 先创建一个临时 placeholder 占位
    ph = check("PLACEHOLDER", "POST", "/api/novels", {"title": "_smoke_placeholder"}, expect=(200, 201))
    ph_id = ph.get("id") if isinstance(ph, dict) else None
    if ph_id:
        check("SWITCH_AWAY", "POST", f"/api/novels/{ph_id}/switch")
        check("DELETE_NOVEL", "DELETE", f"/api/novels/{novel_id}", expect=(200, 204, 404))
        check("DELETE_PLACEHOLDER", "DELETE", f"/api/novels/{ph_id}", expect=(200, 204, 400, 404))

banner("RESULT")
print(f"PASS {passes}")
print(f"FAIL {len(fails)}")
for f in fails:
    print(f"  - {f}")
sys.exit(0 if not fails else 1)
