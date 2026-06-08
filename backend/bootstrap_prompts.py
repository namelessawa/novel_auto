"""bootstrap_prompts - 5 个启动 prompt 序列(prompts.md 第 13 节)。

冷启动一个新世界,顺序调用:

1. 世界基础设定(seed_description → WorldState)
2. 初代角色集(6-10 个 CharacterProfile + CharacterState)
3. 初始开放伏笔(3-5 个 OpenLoop,至少 1 个 urgency>7)
4. 风格锚点(3-5 段 ~300 字 StyleAnchor)
5. (可选) 第一章

用法:

    python -m backend.bootstrap_prompts \\
        --novel-id mountain \\
        --seed "宋代仿古,边境与中央的张力" \\
        --positioning "古典含蓄、心理白描" \\
        --references "Le Guin / 古龙"

也可设置环境变量 ``ACTIVE_NOVEL_ID`` / ``ACTIVE_NOVEL_DATA_DIR`` 让 Orchestrator
启动时自动接管该 novel。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# 确保 backend 与项目根都在 sys.path 中
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
for p in (_PROJECT_ROOT, _BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    Faction,
    Goal,
    OpenLoop,
    Relationship,
    StyleAnchor,
    TickLocation,
    WorldState,
)
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt 1: WorldState
# ---------------------------------------------------------------------------

PROMPT_WORLD = """\
你即将设计一个用于无限小说生成的虚构世界的初始设定。

# 世界种子

{seed}

# 要求

1. 不要过度设定 - 世界应有"留白"
2. **至少 5 个有名字的地点 (locations)** — 分散在不同类型, 至少要覆盖:
   * 1 个主要城市 / 据点 (角色起点)
   * 1 个边境 / 前线 (冲突地)
   * 1 个秘所 / 神殿 / 旧址 (悬念锚)
   * 1 个旷野 / 自然地 (旅行通道)
   * 1 个聚会点 / 市集 / 港口 (信息交换)
   * 地点 id 用语义化前缀 (loc_city / loc_frontier / loc_temple / loc_wild / loc_market 等),
     不要全用 loc_1, loc_2, ...; 不要把所有角色都堆在一个地点
3. 至少 3 个相互对立的势力 (factions, 支撑长期冲突)
4. 至少 3 个潜在火药桶 (future 可激活的张力)
5. 世界规则不超过 10 条
6. 每个地点的 current_state 至少 20 个汉字, 让 Narrator 一眼能写出气氛

# 输出格式(严格 JSON,不要 markdown 代码块)

{{
  "world_state": {{
    "era": "...",
    "current_season": "...",
    "weather": "...",
    "locations": [
      {{"id": "loc_city", "name": "...", "type": "city", "current_state": "...至少 20 字...", "notable_features": []}},
      {{"id": "loc_frontier", "name": "...", "type": "frontier", "current_state": "...", "notable_features": []}},
      {{"id": "loc_temple", "name": "...", "type": "ruin", "current_state": "...", "notable_features": []}},
      {{"id": "loc_wild", "name": "...", "type": "wilderness", "current_state": "...", "notable_features": []}},
      {{"id": "loc_market", "name": "...", "type": "port", "current_state": "...", "notable_features": []}}
    ],
    "factions": [
      {{"id": "f_1", "name": "...", "description": "...", "territory": ["loc_city"]}}
    ],
    "active_global_events": ["..."],
    "world_rules": ["..."]
  }}
}}
"""


# ---------------------------------------------------------------------------
# Prompt 2: 角色集
# ---------------------------------------------------------------------------

PROMPT_CHARACTERS = """\
基于以下 WorldState 设计 6-10 个起始角色。

```json
{world_state}
```

# 要求

* 3 个 A 级角色(主角候选,深度建模)
* 3-4 个 B 级角色(重要配角)
* 2-3 个 C 级角色(NPC,仅标签)
* 角色间必须已有关系(不要互不相识)
* 每个 A 级角色都要有 arc_goal 和至少 1 个 secret
* 角色与势力的关系应预埋张力

# 输出格式(严格 JSON,不要 markdown 代码块)

{{
  "characters": [
    {{
      "profile": {{
        "id": "char_alice",
        "name": "...",
        "age": 30,
        "role": "主角|配角|NPC",
        "importance_tier": "A|B|C",
        "personality": "...",
        "appearance": "...",
        "speech_style": "...",
        "core_values": ["..."],
        "fears": ["..."],
        "desires": ["..."]
      }},
      "state": {{
        "character_id": "char_alice",
        "current_location": "loc_1",
        "current_goals": [
          {{"id": "g1", "description": "...", "priority": 7, "progress": 0.0, "obstacles": []}}
        ],
        "arc_goal": "...",
        "known_facts": ["..."],
        "secrets_kept": ["..."],
        "relationships": {{
          "char_bob": {{"with_character_id": "char_bob", "type": "朋友|敌人|恋人|...", "trust": 5, "history_summary": "...", "last_interaction_tick": 0}}
        }},
        "emotional_state": "...",
        "inventory": [],
        "status_effects": []
      }}
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Prompt 3: OpenLoops
# ---------------------------------------------------------------------------

PROMPT_LOOPS = """\
基于 WorldState 和角色集,预设 3-5 个开放伏笔(OpenLoop) 作为故事初始燃料。

```json
{world_state}
```

```json
{characters}
```

# 要求

* description (具体的悬念)
* involved_characters (相关角色 id)
* type: mystery / conflict / promise / threat
* urgency: 0-10
* 至少应有一个伏笔 urgency >7(驱动早期情节)
* 至少一个伏笔涉及超过 2 个角色

# 输出格式(严格 JSON,不要 markdown 代码块)

{{
  "open_loops": [
    {{
      "id": "loop_1",
      "description": "...",
      "involved_characters": ["char_alice", "char_bob"],
      "urgency": 8,
      "type": "mystery|conflict|promise|threat"
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Prompt 4: StyleAnchor
# ---------------------------------------------------------------------------

PROMPT_STYLE = """\
以下是这部连载小说的风格设定。

# 作品定位

{positioning}

# 参考作家/作品

{references}

请生成 3-5 段风格锚点示例,每段约 300 字,模拟 Narrator 未来产出时应有的腔调。
这些段落将作为 Narrator 每次调用时的 style_anchors 参数。

# 要求

* 不同类型的场景各一段(对话场、动作场、独处心理场、自然描写场)
* 体现明确的句长偏好和修辞密度
* 避免任何"AI 写作癖好"

# 输出格式(严格 JSON,不要 markdown 代码块)

{{
  "style_anchors": [
    {{
      "excerpt": "...约 300 字的段落...",
      "selection_reason": "为什么选这段做锚点",
      "weight": 1.0,
      "scene_type": "dialogue|action|inner_monologue|nature|general"
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


async def _llm_json(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4096,
    *,
    stage: str = "unknown",
) -> dict:
    """统一 LLM 调用 + JSON 解析。stage 用于 token budget 归账 (world/characters/loops/style)。"""
    resp = await llm_client.chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.7,
        max_tokens=max_tokens,
        agent_id=f"bootstrap:{stage}",
        priority="medium",
        tick=0,
    )
    text = resp.content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


async def bootstrap_world(
    *,
    novel_id: str,
    data_dir: str,
    seed: str,
    positioning: str,
    references: str,
) -> TickState:
    """完整冷启动序列。返回填充好的 TickState 实例(已 save)。"""
    logger.info("Bootstrapping novel '%s' (data_dir=%s)", novel_id, data_dir)
    ts = TickState(data_dir=data_dir)

    # === Step 1: WorldState ============================================
    logger.info("[1/4] Generating WorldState…")
    world_resp = await _llm_json(
        system_prompt="你是一个虚构世界设计师。严格按要求输出 JSON。",
        user_prompt=PROMPT_WORLD.format(seed=seed),
        max_tokens=24576,
        stage="world",
    )
    ws = WorldState.model_validate(world_resp.get("world_state", {}))
    # v2.16 — 多地点校验: <3 个有效 location 时世界过薄, 长期会让所有角色挤在一处。
    # 不阻断 bootstrap (LLM 偶发偷工不该让冷启动整条链炸掉), 但 warning 必须可见。
    if len(ws.locations) < 3:
        logger.warning(
            "WorldState locations=%d (<3) — 世界过薄, 角色会挤在单一地点; "
            "考虑重跑或手动补地点。",
            len(ws.locations),
        )
    elif len(ws.locations) < 5:
        logger.warning(
            "WorldState locations=%d (<5) — 已可用但偏少, 建议补到 5 个以上",
            len(ws.locations),
        )
    ts.set_world_state(ws)
    logger.info(
        "  → era=%s, locations=%d, factions=%d, rules=%d",
        ws.era,
        len(ws.locations),
        len(ws.factions),
        len(ws.world_rules),
    )

    # === Step 2: Characters ===========================================
    logger.info("[2/4] Generating characters…")
    chars_resp = await _llm_json(
        system_prompt="你是一个角色设计师。严格按要求输出 JSON。",
        user_prompt=PROMPT_CHARACTERS.format(
            world_state=ws.model_dump_json(indent=2)
        ),
        max_tokens=32768,
        stage="characters",
    )
    main_tracking_id: str | None = None
    for char_item in chars_resp.get("characters", []) or []:
        try:
            profile = CharacterProfile.model_validate(char_item.get("profile", {}))
            state = CharacterState.model_validate(char_item.get("state", {}))
            ts.upsert_character_profile(profile)
            ts.upsert_character_state(state)
            if profile.importance_tier == "A" and main_tracking_id is None:
                main_tracking_id = profile.id
        except Exception as e:
            logger.warning("Skip invalid character (%s): %s", e, char_item)

    if main_tracking_id is None and ts.list_character_profiles():
        # 没 A 级角色则取第一个
        main_tracking_id = ts.list_character_profiles()[0].id

    logger.info("  → %d characters created", len(ts.list_character_profiles()))

    # === Step 3: OpenLoops ===========================================
    logger.info("[3/4] Generating OpenLoops…")
    loops_resp = await _llm_json(
        system_prompt="你是一个剧情设计师。严格按要求输出 JSON。",
        user_prompt=PROMPT_LOOPS.format(
            world_state=ws.model_dump_json(indent=2),
            characters=json.dumps(
                [
                    {"id": p.id, "name": p.name, "tier": p.importance_tier}
                    for p in ts.list_character_profiles()
                ],
                ensure_ascii=False,
                indent=2,
            ),
        ),
        max_tokens=12288,
        stage="open_loops",
    )
    for loop_raw in loops_resp.get("open_loops", []) or []:
        try:
            loop_raw.setdefault("opened_tick", 0)
            loop_raw.setdefault("id", f"loop_{uuid.uuid4().hex[:8]}")
            ts.add_open_loop(OpenLoop.model_validate(loop_raw))
        except Exception as e:
            logger.warning("Skip invalid OpenLoop (%s): %s", e, loop_raw)
    logger.info("  → %d OpenLoops added", ts.get_open_loop_count())

    # === Step 4: StyleAnchors ========================================
    logger.info("[4/4] Generating StyleAnchors…")
    style_resp = await _llm_json(
        system_prompt="你是一个文风顾问。严格按要求输出 JSON。",
        user_prompt=PROMPT_STYLE.format(
            positioning=positioning,
            references=references,
        ),
        max_tokens=16384,
        stage="style",
    )
    for anchor_raw in style_resp.get("style_anchors", []) or []:
        try:
            ts.add_style_anchor(StyleAnchor.model_validate(anchor_raw))
        except Exception as e:
            logger.warning("Skip invalid StyleAnchor (%s): %s", e, anchor_raw)
    logger.info("  → %d StyleAnchors registered", len(ts.list_style_anchors()))

    # 保存 main_tracking_character_id 到 ENV-style 配置(供 Orchestrator 读取)
    if main_tracking_id:
        env_file = Path(data_dir) / "bootstrap.env"
        env_file.write_text(
            f"ACTIVE_NOVEL_ID={novel_id}\n"
            f"ACTIVE_NOVEL_DATA_DIR={data_dir}\n"
            f"MAIN_TRACKING_CHARACTER_ID={main_tracking_id}\n",
            encoding="utf-8",
        )
        logger.info("  → bootstrap.env written: main tracking = %s", main_tracking_id)

    ts.save()
    logger.info("Bootstrap complete. tick=%d", ts.current_tick)
    return ts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="冷启动一个新虚构世界")
    parser.add_argument("--novel-id", required=True, help="小说 id (用作数据目录名)")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="数据目录,默认 backend/data/novels/<id>",
    )
    parser.add_argument("--seed", required=True, help="世界种子描述")
    parser.add_argument(
        "--positioning",
        default="古典含蓄、心理白描、节奏舒缓、避免华丽辞藻",
        help="作品定位",
    )
    parser.add_argument(
        "--references",
        default="Le Guin / 古龙",
        help="参考作家/作品",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    data_dir = args.data_dir or os.path.join(
        _BACKEND_DIR, "data", "novels", args.novel_id
    )
    os.makedirs(data_dir, exist_ok=True)

    asyncio.run(
        bootstrap_world(
            novel_id=args.novel_id,
            data_dir=data_dir,
            seed=args.seed,
            positioning=args.positioning,
            references=args.references,
        )
    )
    # Windows GBK 控制台无法编码 ✓ — 用 ASCII 替代
    print(f"[OK] Bootstrap complete: {data_dir}")
    print(f"  启动 backend: ACTIVE_NOVEL_DATA_DIR={data_dir} python run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
