"""bootstrap_prompts - 5 个启动 prompt 序列(prompts.md 第 13 节)。

冷启动一个新世界,顺序调用:

1. 世界基础设定(seed_description → WorldState)
2. 初代角色集(默认 3 个: 1A+2B+0C, Phase 3-B 实测 sweet spot;
   可用 --cast-{a,b,c}-count 覆盖, all-or-nothing)
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
    OpenLoop,
    StyleAnchor,
    WorldState,
)
from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt 1: WorldState
# ---------------------------------------------------------------------------

PROMPT_WORLD = """\
设计无限连载小说的虚构世界初始设定.

# 作品标题
{title}

# 世界种子
{seed}

# 标题约束 (强制)

世界设计**必须**与作品标题语义一致 — 含"神明/魔法/龙/仙"→奇幻/修真;
含"星舰/AI/殖民"→科幻; 含"民国/武侠"→对应历史. 不要因种子简短就退化
为"中世纪村庄"或"现代都市". era / world_rules 至少一条呼应标题关键词.

# 要求

1. 世界要有"留白", 不过度设定
2. **≥5 个有名字的地点** — 覆盖: 1 主城/据点 (角色起点) / 1 边境前线
   (冲突地) / 1 秘所神殿旧址 (悬念锚) / 1 旷野自然 (旅行通道) /
   1 市集港口 (信息交换). id 用语义前缀 (loc_city / loc_frontier /
   loc_temple / loc_wild / loc_market), 不要 loc_1/loc_2.
3. ≥3 个相互对立的势力 (factions, 支撑长期冲突)
4. ≥3 个潜在火药桶 (future 可激活张力)
5. world_rules ≤ 10 条
6. 每个 location.current_state ≥ 20 字, 让 Narrator 一眼写得出气氛

# 输出格式 (严格 JSON, 不要 markdown 代码块)

所有 "<...>" 都是占位符 — 必须替换为根据本作品标题+种子真正设计的内容,
绝不可保留 "<...>" 或任何示意性字符串.

{{
  "world_state": {{
    "era": "<根据本作品标题/种子设计的纪元名>",
    "current_season": "<季节>",
    "weather": "<本季典型天气>",
    "locations": [
      {{"id": "loc_city", "name": "<主城名>", "type": "city", "current_state": "<≥20 字描述当前状态、氛围、可见物>", "notable_features": []}},
      {{"id": "loc_frontier", "name": "<边境地名>", "type": "frontier", "current_state": "<...>", "notable_features": []}},
      {{"id": "loc_temple", "name": "<秘所名>", "type": "ruin", "current_state": "<...>", "notable_features": []}},
      {{"id": "loc_wild", "name": "<旷野名>", "type": "wilderness", "current_state": "<...>", "notable_features": []}},
      {{"id": "loc_market", "name": "<市集名>", "type": "port", "current_state": "<...>", "notable_features": []}}
    ],
    "factions": [
      {{"id": "f_1", "name": "<势力名>", "description": "<...>", "territory": ["loc_city"]}}
    ],
    "active_global_events": [],
    "world_rules": []
  }}
}}
"""


# ---------------------------------------------------------------------------
# Prompt 2: 角色集
# ---------------------------------------------------------------------------

PROMPT_CHARACTERS = """\
基于以下 WorldState 设计起始角色: {cast_breakdown}.

```json
{world_state}
```

# 要求

* {cast_tiers}
* 角色间必须已有关系 (不要互不相识); A 级必须有 arc_goal 和 ≥1 secret
* 角色与势力关系要预埋张力; A/B 之间至少两对欲望互相冲突
* **名字**: 与世界观语言一致 (中文世界用中文名); id 用拼音 slug
  (char_linxue, char_sumo)
* **speech_style 含 2 句示例台词** ("特征描述. 例: 「...」「...」") —
  两个角色台词放一起必须一眼能分辨 (用词/句长/语气差异)
* **personality 写行为倾向, 不写标签** — "谨慎"❌; "先数清出口再进屋,
  不信口头承诺"✓

# 输出格式 (严格 JSON, 不要 markdown 代码块)

所有 "<...>" 都是占位符 — 必须替换为根据 WorldState 真正设计的角色字段,
id 用真实的拼音 slug (char_xxx, xxx 是角色真名拼音), 绝不保留 "<...>" 或
示意性字符串.

{{
  "characters": [
    {{
      "profile": {{
        "id": "char_<角色名拼音>",
        "name": "<角色中文名>",
        "age": 0,
        "role": "<主角|配角|NPC>",
        "importance_tier": "<A|B|C>",
        "personality": "<行为倾向描写, 不写'谨慎'这种标签>",
        "appearance": "<...>",
        "speech_style": "<特征描述. 例: 「...」「...」>",
        "core_values": [],
        "fears": [],
        "desires": []
      }},
      "state": {{
        "character_id": "char_<同上>",
        "current_location": "<现所在 location_id>",
        "current_goals": [
          {{"id": "g1", "description": "<...>", "priority": 7, "progress": 0.0, "obstacles": []}}
        ],
        "arc_goal": "<...>",
        "known_facts": [],
        "secrets_kept": [],
        "relationships": {{
          "char_<其他人>": {{"with_character_id": "char_<其他人>", "type": "<朋友|敌人|...>", "trust": 5, "history_summary": "<...>", "last_interaction_tick": 0}}
        }},
        "emotional_state": "<...>",
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

# 作品标题 (首要锚 — 决定锚点示例的题材与场景)

{title}

# 作品定位 (语感偏好 — 只影响句长 / 词汇密度 / 修辞密度)

{positioning}

# 参考作家/作品 (语感偏好)

{references}

请生成 3-5 段风格锚点示例,每段约 300 字,模拟 Narrator 未来产出时应有的腔调。
这些段落将作为 Narrator 每次调用时的 style_anchors 参数。

锚点示例的角色、场景、张力, 都应当能在《标题》所暗示的世界里真实发生 ——
不要写出与标题题材无关的场景 (例如标题是奇幻/动作向, 却写茶室静坐)。
positioning 与 references 只决定句长、词汇密度、修辞密度等语感层面。

# 要求

* 不同类型的场景各一段(对话场、动作场、独处心理场、自然描写场)
* **对话场锚点必须含 4 句以上你来我往的真实对白** (有动作节拍穿插, 不是引语堆叠) —
  Narrator 将以它为对白密度基准; 没有对白示范的锚点集会把全书带成无对话的独白流
* **动作场锚点以动词驱动**, 短句为主, 出现具体的身体接触/器物/位移
* 每段都应能在该作品的真实世界中发生 (角色 / 场景 / 张力贴合标题)
* 体现明确的句长偏好和修辞密度
* 避免任何"AI 写作癖好" (不写"仿佛""缓缓地""内心深处"之类套话)

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
    raw = resp.content.strip()
    try:
        return parse_llm_json(raw)
    except json.JSONDecodeError as e:
        logger.error(
            "bootstrap stage=%s JSON parse failed at line %d col %d: %s\n"
            "  raw[:500]=%r",
            stage,
            e.lineno,
            e.colno,
            e.msg,
            raw[:500],
        )
        raise


async def generate_style_anchors(
    *,
    title: str,
    positioning: str,
    references: str,
) -> list[StyleAnchor]:
    """单独执行 Step 4 (风格锚点生成). 供 regenerate-style-anchors 端点复用 —
    bootstrap 全流程不变, 这里只跑文风那一阶段, 让上层用新的 prompt 与 title
    重新生成 style_anchors 替换盘上的旧数据."""
    style_resp = await _llm_json(
        system_prompt="你是一个文风顾问。严格按要求输出 JSON。",
        user_prompt=PROMPT_STYLE.format(
            title=title or "(未指定标题 — 根据 positioning / references 自由发挥)",
            positioning=positioning,
            references=references,
        ),
        # v2.38 (iter#31) — 与正常 bootstrap style stage 一致 (4096), 此前
        # regenerate-style 单走的 path 漏修.
        max_tokens=4096,
        stage="regenerate_style",
    )
    anchors: list[StyleAnchor] = []
    for anchor_raw in style_resp.get("style_anchors", []) or []:
        try:
            anchors.append(StyleAnchor.model_validate(anchor_raw))
        except Exception as e:
            logger.warning("Skip invalid StyleAnchor (%s): %s", e, anchor_raw)
    return anchors


async def bootstrap_world(
    *,
    novel_id: str,
    data_dir: str,
    seed: str,
    positioning: str,
    references: str,
    title: str = "",
    cast_a_count: int | None = None,
    cast_b_count: int | None = None,
    cast_c_count: int | None = None,
) -> TickState:
    """完整冷启动序列。返回填充好的 TickState 实例(已 save)。

    ``title`` v2.34 — 作品标题. 同步写入 TickState 让 Narrator 每 tick 拿到,
    并注入 PROMPT_WORLD 强制世界设定与标题语义一致 (修"被遗忘的神明与最后的
    魔法少女" 跑出现实村庄的脱节问题)。
    """
    logger.info("Bootstrapping novel '%s' (data_dir=%s)", novel_id, data_dir)
    ts = TickState(data_dir=data_dir)
    # 早早写入标题, 即便后续 LLM 阶段炸了也不丢
    if title:
        ts.set_novel_title(title)

    # === Step 1: WorldState ============================================
    logger.info("[1/4] Generating WorldState…")
    world_resp = await _llm_json(
        system_prompt="你是一个虚构世界设计师。严格按要求输出 JSON。",
        user_prompt=PROMPT_WORLD.format(
            seed=seed, title=title or "(未指定 — 请根据 seed 自由发挥)"
        ),
        # v2.38 (iter#11) — WorldState JSON ~3000 tokens 完成 (era/locations/
        # factions/world_rules 加起来 ~5 个地点 + 3 派系 + 6 规则). 24576 是
        # reasoning 浪费值.
        max_tokens=4096,
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
    # iter#119 Phase 3-B + iter#123 review + iter#128 default 改:
    # 模式:
    #   * 0/3 设 → cast=3 sweet spot (1A+2B+0C), Phase 3-B 实测默认
    #     (旧 wide range 6-10 在 iter#128 退役 — 跨 3-seed -8.3% cost)
    #   * 3/3 设 → "恰好 N 角色 (固定)", 跨 seed bench 实验可控
    #   * 1-2/3 设 → 拒绝 (ValueError). 部分设容易让用户以为只指定 A 数,
    #     却被 b/c 默认值悄悄加成, 破坏 bench 复现性. all-or-nothing.
    set_count = sum(
        x is not None for x in (cast_a_count, cast_b_count, cast_c_count)
    )
    if set_count == 0:
        # iter#128 Phase 3-B verdict: cast=3 (1A+2B+0C) universal sweet spot.
        # 跨 3-seed × 50-tick × 2 cast 模式 实测 vs cast=5: -4.6% avg cost,
        # avg_urg +7.1% (seed3), drift 0/0. vs close-fix wide: -8.3% avg.
        # 历史 wide range "6-10 / 3A+3-4B+2-3C" 改为 "3 / 1A+2B+0C" 默认.
        # iter#129 review MEDIUM: prompt 去 "Phase 3-B" 内部 taxonomy 漏入.
        cast_breakdown = "3 个起始角色 (推荐配置)"
        cast_tiers = (
            "1 个 A 级 (主角, 深度建模) / 2 个 B 级 (重要配角) / "
            "0 个 C 级 (本作不使用 NPC 角色, 必要时 narrate 即可)"
        )
    elif set_count == 3:
        total = cast_a_count + cast_b_count + cast_c_count
        cast_breakdown = f"恰好 {total} 个起始角色 (固定)"
        cast_tiers = (
            f"恰好 {cast_a_count} 个 A 级 (主角候选, 深度建模) / "
            f"恰好 {cast_b_count} 个 B 级 (重要配角) / "
            f"恰好 {cast_c_count} 个 C 级 (NPC)"
        )
    else:
        raise ValueError(
            f"cast 三个参数必须 all-or-nothing (--cast-a/b/c-count). "
            f"目前 {set_count}/3 设, 防止部分设悄悄混 default."
        )

    chars_resp = await _llm_json(
        system_prompt="你是一个角色设计师。严格按要求输出 JSON。",
        user_prompt=PROMPT_CHARACTERS.format(
            # v2.38 (iter#29) — 不缩进 JSON, 节省 ~30% input tokens.
            world_state=ws.model_dump_json(),
            cast_breakdown=cast_breakdown,
            cast_tiers=cast_tiers,
        ),
        # v2.38 (iter#11) — characters JSON 4-6 角色 × ~700 tokens = ~4000.
        max_tokens=6144,
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

    # iter#129 review MEDIUM: cast count compliance check (warning only).
    # LLM 偶发漏 / 多 cast 数 (iter#122 seed1 cast=5 实测得 4). 校验 actual
    # 与请求是否一致, 不匹配 warn 让 bench 实验复现性可追溯, 不阻断主流程.
    if set_count == 3:
        actual_tiers = {"A": 0, "B": 0, "C": 0}
        for p in ts.list_character_profiles():
            tier = (p.importance_tier or "").upper()
            if tier in actual_tiers:
                actual_tiers[tier] += 1
        requested = {
            "A": cast_a_count, "B": cast_b_count, "C": cast_c_count,
        }
        if actual_tiers != requested:
            logger.warning(
                "cast count mismatch — requested %s, actual %s. "
                "LLM 偷工/超发, 不阻断 bootstrap, 但 bench 复现性需注意.",
                requested, actual_tiers,
            )

    logger.info("  → %d characters created", len(ts.list_character_profiles()))

    # === Step 3: OpenLoops ===========================================
    logger.info("[3/4] Generating OpenLoops…")
    loops_resp = await _llm_json(
        system_prompt="你是一个剧情设计师。严格按要求输出 JSON。",
        user_prompt=PROMPT_LOOPS.format(
            # v2.38 (iter#29) — 不缩进 JSON.
            world_state=ws.model_dump_json(),
            characters=json.dumps(
                [
                    {"id": p.id, "name": p.name, "tier": p.importance_tier}
                    for p in ts.list_character_profiles()
                ],
                ensure_ascii=False,
            ),
        ),
        # v2.38 (iter#11) — 3-5 loops × ~500 tokens ≈ 2500 (实测部分模型 loop
        # description 偏长). 3072 太紧会截断, 5120 安全余量.
        max_tokens=5120,
        stage="open_loops",
    )
    raw_loops = loops_resp.get("open_loops", []) or []
    requested_count = len(raw_loops)
    for loop_raw in raw_loops:
        # v2.38 (iter#39) — 与 narrator iter#38 同, LLM 可能写成 str 而非 dict.
        if isinstance(loop_raw, str):
            loop_raw = {"description": loop_raw[:200]}
        elif not isinstance(loop_raw, dict):
            logger.warning("Skip invalid OpenLoop (not dict/str): %r", loop_raw)
            continue
        try:
            loop_raw.setdefault("opened_tick", 0)
            loop_raw.setdefault("id", f"loop_{uuid.uuid4().hex[:8]}")
            ts.add_open_loop(OpenLoop.model_validate(loop_raw))
        except Exception as e:
            logger.warning("Skip invalid OpenLoop (%s): %s", e, loop_raw)
    n_loops = ts.get_open_loop_count()
    logger.info("  → %d OpenLoops added", n_loops)
    # v2.38 (iter#12 review fix) — < 3 个伏笔是 event_injector 必须每 tick
    # 注入张力的阈值, bootstrap 阶段就低于此值意味着冷启动剧情骨架薄弱.
    if n_loops < 3:
        logger.warning(
            "Bootstrap 完成但 OpenLoops=%d < 3 (LLM 返回 %d 条但部分 invalid). "
            "EventInjector 会被迫每 tick 注入张力事件. 考虑重跑 bootstrap "
            "或手动补 loops.",
            n_loops, requested_count,
        )

    # === Step 4: StyleAnchors ========================================
    logger.info("[4/4] Generating StyleAnchors…")
    style_resp = await _llm_json(
        system_prompt="你是一个文风顾问。严格按要求输出 JSON。",
        user_prompt=PROMPT_STYLE.format(
            title=title or "(未指定标题 — 根据 positioning / references 自由发挥)",
            positioning=positioning,
            references=references,
        ),
        # v2.38 (iter#11) — 3-5 style_anchors × ~400 tokens ≈ 2000.
        max_tokens=4096,
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

    # v2.35 — 完整性闸: 4 阶段表面成功但内容近乎空 (LLM 返回形对内空的残缺
    # JSON, model_validate 用默认值兜底, task 被无声标 completed 留下"标题+
    # 空设定"的垃圾世界) — Narrator 上场只能瞎写, 内容与标题完全脱钩。
    # 任一关键集合空 = 视为失败, 抛出让 task 状态变 failed, 用户可见可重跑。
    n_chars = len(ts.list_character_profiles())
    n_locs = len(ts.world_state.locations)
    n_loops = ts.get_open_loop_count()
    n_anchors = len(ts.list_style_anchors())
    if n_chars == 0 or n_locs == 0 or n_loops == 0 or n_anchors == 0:
        raise RuntimeError(
            "bootstrap 完成但世界几乎为空 — LLM 返回形对内空的 JSON, "
            f"角色={n_chars} / 地点={n_locs} / 伏笔={n_loops} / 风格锚点={n_anchors}; "
            "请检查 LLM provider / max_tokens 设置或重新触发 bootstrap"
        )
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
        "--title",
        default="",
        help="作品标题 (v2.34 — 注入 PROMPT_WORLD + 后续 Narrator user_prompt)",
    )
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
    # iter#119 Phase 3-B cast-confound 控制 — 跨 seed bench 实验 cast 可控.
    # 不设则默认 wide range (与历史 bench 等价).
    parser.add_argument(
        "--cast-a-count", type=int, default=None,
        help="精确 A 级角色数 (主角候选). 不设则 LLM 自由 (默认 3 个 wide)",
    )
    parser.add_argument(
        "--cast-b-count", type=int, default=None,
        help="精确 B 级角色数 (重要配角). 不设则 LLM 自由 (默认 3-4 个 wide)",
    )
    parser.add_argument(
        "--cast-c-count", type=int, default=None,
        help="精确 C 级角色数 (NPC). 不设则 LLM 自由 (默认 2-3 个 wide)",
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
            title=args.title,
            cast_a_count=args.cast_a_count,
            cast_b_count=args.cast_b_count,
            cast_c_count=args.cast_c_count,
        )
    )
    # Windows GBK 控制台无法编码 ✓ — 用 ASCII 替代
    print(f"[OK] Bootstrap complete: {data_dir}")
    print(f"  启动 backend: ACTIVE_NOVEL_DATA_DIR={data_dir} python run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
