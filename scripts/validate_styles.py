"""对全部 StylePreset 做可恢复的真实生成回归。

特性：同一 theme 只冷启动一次并复制状态；pressure/compatible 双场景；每个
style 记录版本与 prompt hash；确定性验收恒跑；可 ``--no-judge``；失败最多
一次定向修订；每完成一个 style 原子 checkpoint，``--resume`` 可续跑。

示例：
  python scripts/validate_styles.py --provider-file coding.txt --mode both --ticks 1
  python scripts/validate_styles.py --resume docs/iter/style-validation-....json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]


COMPATIBLE_THEME: dict[str, str] = {
    "literary": "scifi_soft_lit",
    "xianxia_fast": "xianxia_cultivation",
    "colloquial_web": "system_cheat",
    "hot_blooded": "mecha_pilot",
    "somber": "republic_spy",
    "lyrical_poetic": "ancient_romance",
    "noir_cold": "republic_spy",
    "black_humor": "workplace_drama",
    "warm_healing": "gourmet_culinary",
    "melancholic": "campus_youth",
    "first_person_immersive": "urban_mystery",
    "ensemble_epic": "history_military",
    "classical_chapter": "wuxia_jianghu",
    "philosophical_meditative": "scifi_soft_lit",
    "screenplay_visual": "mecha_pilot",
    "rough_grit_realism": "apocalypse_wasteland",
}


COMPATIBLE_SCENE: dict[str, str] = {
    "xianxia_fast": "守关者扣住通行令，主角必须当场夺回并用它打开山门，更强追兵已经逼近。",
    "hot_blooded": "同伴被压在断梁下，主角第一次冲锋受阻，必须站起来再次出手。",
    "black_humor": "办事处规定必须先证明自己尚未饿死才能领取口粮，工作人员认真执行荒谬流程。",
    "warm_healing": "灶台边碗裂了、汤快凉了，两个人借修补和分享食物化开一场小误会。",
    "somber": "一封迟到多年的信和一颗旧扣子摆在桌上，收信人必须决定是否拆开。",
    "melancholic": "末班车将开，角色仍拿着没送出去的礼物，知道等待的人不会来了。",
    "classical_chapter": "旧友持信物登门，道出一桩未了约定；门外又传来新的急报。",
    "screenplay_visual": "警示灯熄灭，角色隔门对话并迅速交换位置，门后出现新的动静。",
    "noir_cold": "雨夜交接出现错误暗号，角色不动声色地检查信封和对方的手。",
    "first_person_immersive": "停电后门外有人用熟悉的节奏敲门，我只能依据听见和触到的线索判断。",
    "ensemble_epic": "当前角色收到三方互相矛盾的战报，另一位主角的信物夹在其中。",
    "philosophical_meditative": "角色发现地图上自己的名字每天移动一格，镜中的时钟却始终停在昨天。",
    "lyrical_poetic": "角色在河边归还一件旧物，水声、触感与一句未说完的话共同推进告别。",
    "rough_grit_realism": "补给车陷进泥沟，饥饿的人们必须用磨破的绳索和受伤的肩膀把它拖出。",
    "colloquial_web": "门禁突然失灵，角色必须在管理员赶来前把关键物件取出来。",
    "literary": "角色发现杯底压着一张旧便条，必须在来客进门前决定收起还是摊开。",
}


# 连续验证专用：每个 tick 明确声明前态与本 tick 的唯一增量，避免测试夹具
# 自己反复投喂同一事件。这样仍发生重启时，责任可以归到 Narrator/编辑链路。
PRESSURE_SEQUENCE: tuple[str, ...] = (
    "警报响起，唯一出口将在三分钟后封死；同伴受伤，关键地图被守门者扣住，主角必须立即夺回。",
    "承接上一段：地图已经夺回，原出口也已经封死。主角背着伤员改走锈蚀通风井；井盖正在闭合，本段只写突围的新动作与代价。",
    "承接上一段：众人已经爬上屋顶，不能回到门内或再次夺图。伤员突然倒下，地图又因雨水损坏，主角必须决定救人还是抢在封城前赶路。",
    "承接上一段：主角已带幸存者抵达城墙外，损坏的地图仍在主角手中。守门人提出以地图换入城，本段完成谈判并留下一个新的具体代价。",
    "承接上一段：众人已经进城且交易完成。地图残缺处显出一条来自旧时代的警告，主角据此改变下一步计划；不得重演封门、夺图或入城。",
    "承接上一段：计划已经改变。用一次低强度照料或关系选择收束本节，同时保留警告背后的问题；不得新增袭击来强造高潮。",
)
SEQUENCE_IMPORTANCE: tuple[int, ...] = (10, 8, 6, 7, 5, 5)
PRESSURE_SEQUENCE_CONSEQUENCES: tuple[tuple[str, ...], ...] = (
    (
        "本段结束前：地图由主角一方持有",
        "本段结束前：主角与伤员已越过出口，原出口已封死",
    ),
    (
        "本段结束前：两人已离开通风井，抵达屋顶或厂外",
        "本段结束前：井盖已闭合，地图仍由主角一方持有",
    ),
    (
        "本段结束前：两人已到达城墙外",
        "本段结束前：地图因雨水受损，但仍由主角一方持有",
        "本段结束前：主角选择带着伤员继续赶路",
    ),
    (
        "本段结束前：守门人已主动提出以地图换入城",
        "本段结束前：地图已交给守门人，两人已进入城内",
        "本段结束前：谈判产生一项正文明写的新代价",
    ),
    ("本段结束前：主角已根据旧时代警告改变计划",),
    ("本段结束前：一次照料或关系选择已完成，没有新增袭击",),
)


def configure_provider_runtime(path: Path):
    """Parse a read-only provider file without mutating ambient context."""
    from nf_core.provider_runtime import ProviderRuntimeConfig

    return ProviderRuntimeConfig.from_provider_file(path)


def _configure_provider(path: Path):
    """Backward-compatible name for existing validation entry points."""
    return configure_provider_runtime(path)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _usage_snapshot() -> dict[str, Any]:
    """Copy the global token tracker; never retain its mutable snapshot."""
    from nf_core.token_budget import get_global_tracker

    snap = get_global_tracker().snapshot
    return {
        "prompt_tokens": int(snap.total_prompt_tokens),
        "completion_tokens": int(snap.total_completion_tokens),
        "cached_tokens": int(snap.total_cached_tokens),
        "call_count": int(snap.call_count),
        "by_agent": dict(snap.by_agent),
    }


def _usage_delta(before: dict, after: dict, duration_sec: float) -> dict:
    agents = set(before.get("by_agent", {})) | set(after.get("by_agent", {}))
    by_agent = {
        agent: max(
            0,
            int(after.get("by_agent", {}).get(agent, 0))
            - int(before.get("by_agent", {}).get(agent, 0)),
        )
        for agent in sorted(agents)
    }
    by_agent = {agent: tokens for agent, tokens in by_agent.items() if tokens}
    calls = max(0, int(after.get("call_count", 0)) - int(before.get("call_count", 0)))
    prompt = max(
        0, int(after.get("prompt_tokens", 0)) - int(before.get("prompt_tokens", 0))
    )
    completion = max(
        0,
        int(after.get("completion_tokens", 0))
        - int(before.get("completion_tokens", 0)),
    )
    total = prompt + completion
    attributed = sum(by_agent.values())
    return {
        "duration_sec": round(max(0.0, duration_sec), 3),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "cached_tokens": max(
            0,
            int(after.get("cached_tokens", 0))
            - int(before.get("cached_tokens", 0)),
        ),
        "call_count": calls,
        "usage_status": "MISSING" if calls and not (prompt + completion) else (
            "REPORTED" if calls else "NOT_APPLICABLE"
        ),
        "by_agent": by_agent,
        "unattributed_tokens": max(0, total - attributed),
    }


def _aggregate_cost(blocks: list[dict]) -> dict:
    by_agent: dict[str, int] = {}
    for block in blocks:
        for agent, tokens in (block.get("by_agent", {}) or {}).items():
            by_agent[agent] = by_agent.get(agent, 0) + int(tokens or 0)
    calls = sum(int(block.get("call_count", 0) or 0) for block in blocks)
    prompt = sum(int(block.get("prompt_tokens", 0) or 0) for block in blocks)
    completion = sum(
        int(block.get("completion_tokens", 0) or 0) for block in blocks
    )
    total_tokens = prompt + completion
    missing = sum(block.get("usage_status") == "MISSING" for block in blocks)
    return {
        "duration_sec": round(
            sum(float(block.get("duration_sec", 0.0) or 0.0) for block in blocks), 3
        ),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total_tokens,
        "cached_tokens": sum(
            int(block.get("cached_tokens", 0) or 0) for block in blocks
        ),
        "call_count": calls,
        "usage_status": "PARTIAL" if missing else (
            "REPORTED" if calls else "NOT_APPLICABLE"
        ),
        "by_agent": dict(sorted(by_agent.items())),
        "unattributed_tokens": max(0, total_tokens - sum(by_agent.values())),
        "missing_usage_blocks": missing,
    }


def _render_markdown(report: dict) -> str:
    rows = []
    for item in report.get("results", []):
        rows.append(
            f"| {item['scenario']} | {item['theme']} | {item['style']} | "
            f"{'PASS' if item['accepted'] else 'FAIL'} | {item['char_count']} | "
            f"{item.get('revision_count', 0)} |"
        )
    passed = sum(bool(r.get("accepted")) for r in report.get("results", []))
    cost = (report.get("cost") or {}).get("total") or {}
    return (
        "# Style validation\n\n"
        f"- Git: `{report['metadata']['git_sha']}`\n"
        f"- Model: `{report['metadata']['provider']['model']}`\n"
        f"- Execution path: `{report['metadata'].get('execution_path', 'unknown')}`\n"
        f"- Orchestrator exercised: "
        f"`{report['metadata'].get('orchestrator_exercised', 'unknown')}`\n"
        f"- CanonicalFact sidecar exercised: "
        f"`{report['metadata'].get('canonical_fact_sidecar_exercised', 'unknown')}`\n"
        f"- Passed: **{passed}/{len(report.get('results', []))}**\n\n"
        f"- Cost coverage: `{(report.get('cost') or {}).get('samples_with_cost', 0)}` / "
        f"`{len(report.get('results', []))}` samples\n"
        f"- Tokens: `{cost.get('total_tokens', 'unknown')}` "
        f"(`{cost.get('usage_status', 'UNKNOWN')}`)\n"
        f"- Measured wall time: `{cost.get('duration_sec', 'unknown')}s`\n\n"
        "| Scenario | Theme | Style | Verdict | Chars | Revisions |\n"
        "|---|---|---|---:|---:|---:|\n" + "\n".join(rows) + "\n"
    )


async def _semantic_judge(preset, text: str, *, strict: bool, tick: int) -> dict:
    from nf_core.json_utils import parse_llm_json
    from nf_core.llm_client import llm_client

    resp = await llm_client.chat(
        system_prompt="你是独立小说风格验收员。只按给定契约评判，严格输出 JSON。",
        user_prompt=f"""\
风格：{preset.label} ({preset.key})
严格节拍：{strict}
契约：
{preset.narrator_addendum}
短清单：{preset.final_checklist}

正文：
{text}

请判断风格是否一眼可辨、语义是否兑现、事实是否被风格要求篡改。任何硬契约
未兑现时 pass 必须为 false，不得用总分抵消。严格输出：
{{"pass":true,"score":0到10,"blocking_issues":["未满足的硬契约"],"issues":["非阻断观察"],"rewrite_directive":"失败时的一句定向修订指令"}}
""",
        temperature=0.1,
        max_tokens=900,
        agent_id="style_validation_judge",
        priority="medium",
        tick=tick,
    )
    data = parse_llm_json(resp.content)
    return _normalise_semantic_judge(data)


async def _semantic_sequence_judge(
    preset,
    text: str,
    *,
    ticks: int,
    expected_ticks: int | None = None,
    segments: list[str] | None = None,
    viewpoint_schedule: list[str] | None = None,
) -> dict:
    from nf_core.json_utils import parse_llm_json
    from nf_core.llm_client import llm_client

    annotated_segments = "\n\n".join(
        f"【片段 {index + 1}｜指定视点："
        f"{(viewpoint_schedule or [])[index] if index < len(viewpoint_schedule or []) else '未提供'}】\n"
        f"{segment}"
        for index, segment in enumerate(segments or [])
    )
    resp = await llm_client.chat(
        system_prompt=(
            "你是独立的中文长篇小说验收编辑。检查连续性与风格，不替正文找借口，"
            "严格输出 JSON。"
        ),
        user_prompt=f"""\
风格：{preset.label} ({preset.key})
风格契约：{preset.narrator_addendum}
短清单：{preset.final_checklist}
实际叙述片段：{ticks}；场景素材数量：{expected_ticks or ticks}

【连续正文】
{text}

【原始 tick 边界与指定视点；仅用于判断每段视点和收尾，边界不可自行重分】
{annotated_segments or '未提供；不要猜测段界'}

检查硬项：
1. 先逐段建立人物状态表，明确每个人的伤势部位、存亡、位置、所持物品及数量、
   物资的交易/使用/消耗和已知信息；只有正文写出改变事件才能更新。伤势或物品无事件
   依据转移给另一角色，或已交付/用完/损坏的物资无故恢复，即使只有一句，
   也是 blocking state conflict。
2. 时间、位置、物品和人物状态只能前进，不能把已完成的夺取、交易、开门、
   倒计时、受伤、发现换一种说法重新演一遍。
3. 第一段后的各段不得重新介绍同一危机；转场必须能从前一句直接接着读。
4. 风格在开场、动作、转场和收束中持续可辨，但不能机械重复强格式。契约使用
   “必须/至少/每段/禁”声明的要求未兑现时，必须放入 blocking_issues，
   不得只放在 issues 里。
5. 本节至少形成一条清楚的因果推进，并以阶段性变化而非突然停笔收束。

高精度边界：必须按句子出现顺序判断，不得把前面的动作误说成发生在后面。
角色交付物品后仍可以知道它的性质、提醒新持有者防水/防损；这不代表他仍
持有该物品。物品受潮、字迹洇开不等于所有残迹都不可辨，正文明确保留的半个
箭头仍可被辨认；“展开看一眼”也不等于读懂内容。薄纸放在靴筒且腿部受伤并非
逻辑不可能，除非正文明确写出靴筒封死或无法触及。随身物品经历移动后再次取出
不需要逐场重复交代。角色交出关键物品后，无须另写内心反应或“意识到失去”；
缺少情绪/认知反应不是状态冲突。不得在 state_conflicts 中先承认“这本身不是
状态冲突”，随后又把同一件事包装成硬冲突。没有再次提及伤口/夹板/物品不等于
它消失。角色说“图给你，我们拿什么找路”是在讨论团队交易后果，不等于声称
自己物理持有地图；只有“地图还在我这里/由我保管”等明确陈述才是持有声明。
角色可对同伴提出交付团队物品的建议，无须先取得持有者“授权”，这不是代理权或
物品状态冲突。群像契约的“其他角色”是指定视点之外的一位；两位主角同段行动
已经满足，不要求第三人。契约明许动作/信物/传闻/回忆任一，不能擅自改成必须
当场动作。收尾按带边界文本的最后 1–3 句检查，不得把段中环境句误认成段尾。
只有前后短引文能证明的
硬矛盾才能放入 state_conflicts；不便、风险、可能性低只能列 issues。

任何硬项失败时 pass 必须为 false。严格输出：
{{"pass":true,"score":0到10,"continuity_score":0到10,"style_persistence_score":0到10,"causal_progression_score":0到10,"state_conflicts":[],"blocking_issues":[],"issues":[],"replayed_events":[],"rewrite_directive":"失败时一句定向指令"}}
""",
        temperature=0.0,
        max_tokens=1200,
        agent_id="style_sequence_judge",
        priority="medium",
        tick=ticks,
    )
    return _normalise_semantic_judge(parse_llm_json(resp.content))


def _normalise_semantic_judge(data: dict) -> dict:
    """防 judge 自相矛盾：issues 明示硬缺项时不能仍以高总分 PASS。"""
    result = dict(data)
    score = float(result.get("score", 0) or 0)
    self_negating = re.compile(
        r"不构成(?:物理)?(?:持有|状态)?冲突|非严格状态冲突|这本身不是状态冲突"
    )
    blocking = [
        str(x) for x in (result.get("blocking_issues") or [])
        if str(x).strip() and not self_negating.search(str(x))
    ]
    state_conflicts = [
        str(x) for x in (result.get("state_conflicts") or [])
        if str(x).strip() and not self_negating.search(str(x))
    ]
    if state_conflicts:
        blocking.extend(
            issue for issue in state_conflicts if issue not in blocking
        )
    issues = [str(x) for x in (result.get("issues") or []) if str(x).strip()]
    if not blocking:
        hard_language = re.compile(
            r"缺少|没有(?:完成|出现|体现)|"
            r"未(?:独立|形成|完成|出现|兑现|满足|明确|持续)|"
            r"不符合|违反|必须补|需要补|需单独|状态矛盾|"
            r"数量矛盾|无故恢复|无事件依据|凭空出现|从何而来|"
            r"来源不明"
        )
        blocking = [issue for issue in issues if hard_language.search(issue)]
    result["score"] = score
    result["issues"] = issues
    result["blocking_issues"] = blocking
    result["state_conflicts"] = state_conflicts
    result["pass"] = bool(result.get("pass")) and score >= 7 and not blocking
    if blocking and not str(result.get("rewrite_directive", "") or "").strip():
        result["rewrite_directive"] = "；".join(blocking)
    return result


def _is_transient_generation_failure(narrative_text: str, skip_reason: str) -> bool:
    return not narrative_text and any(
        marker in skip_reason
        for marker in ("LLM 不可用", "Connection error", "Timeout")
    )


def _execution_profile() -> dict[str, object]:
    """Describe the runtime path exercised by this benchmark."""
    return {
        "execution_path": "narrator_direct",
        "orchestrator_exercised": False,
        "canonical_fact_sidecar_exercised": False,
    }


async def _targeted_rewrite(preset, text: str, directive: str, *, tick: int) -> str:
    from nf_core.json_utils import parse_llm_json
    from nf_core.llm_client import llm_client

    resp = await llm_client.chat(
        system_prompt=(
            "你是小说定向修订器。保留事件和因果，只修明确列出的问题，严格输出 JSON。"
        ),
        user_prompt=f"""\
风格契约：{preset.narrator_addendum}
必须修复：{directive}
原正文：{text}
可删除独立成行的 text/markdown/代码围栏；它们是格式残片。若指令包含已有状态
矛盾，只能作最小且全篇一致的状态修复，不能借机新增人物、物品、决定或结果。
输出 {{"narrative_text":"完整修订正文"}}，不要解释。
""",
        temperature=0.25,
        max_tokens=min(5500, max(1400, len(text) * 2)),
        agent_id="style_validation_rewrite",
        priority="critical",
        tick=tick,
    )
    return str(parse_llm_json(resp.content).get("narrative_text", "") or "").strip()


async def _generate_one(
    *, base_dir: Path, work_dir: Path, style_key: str, theme_key: str,
    scenario: str, ticks: int, no_judge: bool, max_revisions: int,
    sequence: bool = False, section_edit: bool = False,
) -> dict:
    from agents.narrator_agent import NarratorAgent
    from bootstrap_prompts import generate_style_anchors
    from memory.tick_state import TickState
    from memory_system.models import Event
    from novel_presets import get_style_preset
    from quality_metrics.style_contract import style_contract_report

    if work_dir.exists():
        raise FileExistsError(work_dir)
    shutil.copytree(base_dir, work_dir)
    ts = TickState(data_dir=str(work_dir))
    if not ts.load():
        raise RuntimeError(f"cloned TickState missing: {work_dir}")
    preset = get_style_preset(style_key)
    ts.set_style_preset_contract(style_key, preset.to_snapshot())
    anchors = await generate_style_anchors(
        title=ts.novel_title,
        positioning=preset.description,
        references="以 preset 契约为准，不模仿具体作者内容",
        style_preset_key=style_key,
        style_preset_snapshot=preset.to_snapshot(),
    )
    ts.replace_style_anchors(anchors)
    ts.save()

    profiles = ts.list_character_profiles()
    profile_map = {p.id: p for p in profiles}
    states = ts.list_character_states()
    world = ts.world_state
    tracking = profiles[0].id if profiles else ""
    participants = [p.id for p in profiles[:2]]
    location = world.locations[0].id if world.locations else ""
    pressure = (
        "警报响起，唯一出口将在三分钟后封死；同伴受伤，关键物件被守门者扣住，"
        "主角必须立即选择、行动并承受可见后果。"
    )
    description = pressure if scenario == "pressure" else COMPATIBLE_SCENE[style_key]

    agent = NarratorAgent(enable_critic=False)
    texts: list[str] = []
    traces: list[dict] = []
    tick_outputs: list[dict] = []
    prose_tail = ""
    for tick in range(1, ticks + 1):
        tick_description = description
        if sequence and scenario == "pressure":
            tick_description = PRESSURE_SEQUENCE[min(tick - 1, len(PRESSURE_SEQUENCE) - 1)]
        elif sequence and tick > 1:
            tick_description = (
                f"承接上一段，只写新的反应、阻力和后果，不重演起点：{description}"
            )
        importance = (
            SEQUENCE_IMPORTANCE[min(tick - 1, len(SEQUENCE_IMPORTANCE) - 1)]
            if sequence
            else 10
        )
        event = Event(
            id=f"style_validation_{scenario}_{tick}", tick=tick, type="dramatic",
            location=location, participants=participants, visible_to=participants,
            description=tick_description, narrative_value=importance,
            narrative_value_hint=importance,
            consequences=list(
                PRESSURE_SEQUENCE_CONSEQUENCES[
                    min(tick - 1, len(PRESSURE_SEQUENCE_CONSEQUENCES) - 1)
                ]
            ) if sequence and scenario == "pressure" else [],
        )
        tick_tracking = tracking
        if style_key == "ensemble_epic" and len(participants) >= 2:
            tick_tracking = participants[(tick - 1) % len(participants)]
        generation_attempts = 0
        while True:
            generation_attempts += 1
            out = await agent.narrate(
                tick=tick, world_time=tick, tracking_character_id=tick_tracking,
                tick_events=[event], char_states=states, recent_chapter_summaries=[],
                open_loops=ts.get_open_loops(top_k=5), style_anchors=anchors,
                last_narration_tick=0, novel_title=ts.novel_title,
                char_profiles=profile_map, world_state=world, prose_tail=prose_tail,
                style_preset_key=style_key,
                style_preset_snapshot=preset.to_snapshot(),
                reader_knowledge=ts.get_reader_knowledge(),
                continuity_state=ts.get_narrative_continuity_state(),
            )
            transient = _is_transient_generation_failure(
                out.narrative_text, out.skip_reason
            )
            if not transient or generation_attempts >= 2:
                break
            await asyncio.sleep(1)
        if out.narrative_text:
            texts.append(out.narrative_text)
            prose_tail = out.narrative_text[-1500:]
            if event.id in out.events_consumed:
                ts.record_reader_fact(
                    event_id=event.id, fact=event.description, tick=tick
                )
            for loop_id in out.open_loops_referenced:
                ts.touch_open_loop(loop_id, tick)
            for loop in out.newly_opened_loops:
                if not ts.has_open_loop(loop.id):
                    ts.add_open_loop(loop)
            if out.continuity_state:
                ts.set_narrative_continuity_state(
                    out.continuity_state,
                    audit=out.continuity_state_audit,
                )
        tick_outputs.append({
            "tick": tick,
            "should_narrate": bool(out.should_narrate),
            "skip_reason": out.skip_reason,
            "generation_attempts": generation_attempts,
            "text": out.narrative_text,
            "style_trace": out.style_contract_trace,
            "continuity_state": out.continuity_state,
            "continuity_guard_trace": out.continuity_guard_trace,
            "events_consumed": out.events_consumed,
            "viewpoint_characters": out.viewpoint_characters,
        })
        traces.append(out.style_contract_trace)
    raw_text = "\n\n".join(texts)
    editor_trace: dict = {}
    text = raw_text
    if section_edit and len(texts) >= 2:
        from agents.section_closer import SectionCloser

        close_out = await SectionCloser().close_section(
            narrative_text=raw_text,
            narrative_parts=texts,
            silent_ticks=[],
            chapter=1,
            section_no=1,
            novel_title=ts.novel_title,
            protected_terms=[p.name for p in profiles if p.name],
            style_contract=preset.narrator_addendum + "\n" + preset.final_checklist,
        )
        text = close_out.final_content
        editor_trace = close_out.editor_trace

    det_reports = []
    for record in tick_outputs:
        segment = str(record.get("text", "") or "")
        if not segment:
            continue
        idx = int(record["tick"])
        det_importance = (
            SEQUENCE_IMPORTANCE[min(idx - 1, len(SEQUENCE_IMPORTANCE) - 1)]
            if sequence
            else 10
        )
        strict_tick = agent._is_strict_style_tick(preset, idx, [Event(
            id=f"det_{idx}", tick=idx, type="dramatic",
            description="", narrative_value=det_importance,
        )])
        det_reports.append(
            style_contract_report(
                style_key, segment, preset.det_rules, strict=strict_tick
            )
        )
    det_requires_rewrite = any(rep.requires_rewrite for rep in det_reports)
    det_payload = {
        "requires_rewrite": det_requires_rewrite,
        "per_tick": [rep.to_dict() for rep in det_reports],
    }
    strict = True
    if no_judge or not text:
        judge = None
    elif len(texts) >= 2:
        profile_names = {
            profile.id: profile.name or profile.id for profile in profiles
        }
        viewpoint_schedule = [
            profile_names.get(
                str((record.get("viewpoint_characters") or [""])[0]),
                str((record.get("viewpoint_characters") or [""])[0]),
            )
            for record in tick_outputs
            if str(record.get("text", "") or "").strip()
        ]
        judge = await _semantic_sequence_judge(
            preset,
            text,
            ticks=len(texts),
            expected_ticks=ticks,
            segments=texts,
            viewpoint_schedule=viewpoint_schedule,
        )
    else:
        judge = await _semantic_judge(preset, text, strict=strict, tick=1)
    missing_sequence_ticks = [
        int(record["tick"])
        for record in tick_outputs
        if sequence and not str(record.get("text", "") or "").strip()
    ]
    missing_continuity_state_ticks = [
        int(record["tick"])
        for record in tick_outputs
        if (
            sequence
            and str(record.get("text", "") or "").strip()
            and not record.get("continuity_state")
        )
    ]
    if missing_sequence_ticks and judge is not None:
        missing_issue = (
            "高价值连续场景未产生正文，缺失 tick: "
            + ",".join(map(str, missing_sequence_ticks))
        )
        judge.setdefault("blocking_issues", []).append(missing_issue)
        judge["pass"] = False
    if missing_continuity_state_ticks and judge is not None:
        judge.setdefault("blocking_issues", []).append(
            "连续正文缺少结尾状态账本，缺失 tick: "
            + ",".join(map(str, missing_continuity_state_ticks))
        )
        judge["pass"] = False
    accepted = (
        bool(text)
        and not missing_sequence_ticks
        and not missing_continuity_state_ticks
        and not det_requires_rewrite
        and (judge is None or bool(judge.get("pass")))
    )
    revisions = 0
    revision_attempts = 0
    initial_text = text
    current_det_requires_rewrite = det_requires_rewrite
    post_rewrite_det_payload: dict = {}
    rewrite_verifier_trace: dict = {}
    rewrite_attempt_traces: list[dict] = []
    can_revise = (
        not accepted
        and text
        and max_revisions > 0
        and not missing_sequence_ticks
        and not missing_continuity_state_ticks
    )
    det_issues = "; ".join(
        f.message for rep in det_reports for f in rep.findings
    )
    verifier_feedback = ""
    while can_revise and not accepted and revision_attempts < max_revisions:
        revision_attempts += 1
        directive_parts = [
            str((judge or {}).get("rewrite_directive", "") or "").strip(),
            det_issues,
        ]
        directive = "\n".join(
            part for index, part in enumerate(directive_parts)
            if part and part not in directive_parts[:index]
        ) or preset.final_checklist
        if verifier_feedback:
            directive += (
                "\n上一次候选被事实守恒验证拒绝。不得重复这些改动："
                + verifier_feedback
                + "。保留原稿早期事实，只修明确指出的后文漂移。"
            )
        candidate = await _targeted_rewrite(
            preset, text, directive, tick=revision_attempts
        )
        attempt_trace: dict = {
            "attempt": revision_attempts,
            "directive": directive[:1200],
            "candidate_chars": len(candidate),
        }
        if candidate:
            from agents.section_editor import SectionEditor

            rewrite_verifier_trace = await SectionEditor().verify_fact_preservation(
                original=text,
                candidate=candidate,
                protected_terms=[p.name for p in profiles if p.name],
                declared_repairs=[directive],
            )
            attempt_trace["verifier"] = rewrite_verifier_trace
        rewrite_attempt_traces.append(attempt_trace)
        if candidate and rewrite_verifier_trace.get("safe", False):
            text = candidate
            revisions += 1
            verifier_feedback = ""
            final_det = style_contract_report(
                style_key, text, preset.det_rules, strict=True
            )
            current_det_requires_rewrite = final_det.requires_rewrite
            post_rewrite_det_payload = final_det.to_dict()
            det_issues = "; ".join(
                finding.message for finding in final_det.findings
            )
            # 修订发生在整节层，只复验语义；原始各 tick 的生产 det 仍保留审计。
            judge = None if no_judge else await _semantic_sequence_judge(
                preset, text, ticks=len(texts), expected_ticks=ticks
            )
            if missing_sequence_ticks and judge is not None:
                judge.setdefault("blocking_issues", []).append(
                    "高价值连续场景未产生正文，缺失 tick: "
                    + ",".join(map(str, missing_sequence_ticks))
                )
                judge["pass"] = False
            if missing_continuity_state_ticks and judge is not None:
                judge.setdefault("blocking_issues", []).append(
                    "连续正文缺少结尾状态账本，缺失 tick: "
                    + ",".join(map(str, missing_continuity_state_ticks))
                )
                judge["pass"] = False
            accepted = (
                not missing_sequence_ticks
                and not missing_continuity_state_ticks
                and not current_det_requires_rewrite
                and (judge is None or bool(judge.get("pass")))
            )
        else:
            feedback_items: list[str] = []
            for key in (
                "original_contradictions",
                "residual_contradictions",
                "fact_changes",
                "causal_changes",
                "knowledge_violations",
            ):
                feedback_items.extend(
                    str(item)
                    for item in (rewrite_verifier_trace.get(key, []) or [])
                )
            verifier_feedback = "；".join(feedback_items)[:1800]
            if not candidate:
                break
    return {
        "scenario": scenario,
        "theme": theme_key,
        "style": style_key,
        "preset_version": preset.version,
        "prompt_hash": preset.prompt_hash,
        "strict_every_ticks": preset.strict_every_ticks,
        "accepted": accepted,
        "char_count": len(text),
        "anchor_count": len(anchors),
        "revision_count": revisions,
        "det_report": det_payload,
        "post_rewrite_det_report": post_rewrite_det_payload,
        "semantic_judge": judge,
        "production_style_traces": traces,
        "tick_outputs": tick_outputs,
        "missing_sequence_ticks": missing_sequence_ticks,
        "missing_continuity_state_ticks": missing_continuity_state_ticks,
        "segments": texts,
        "raw_text": raw_text if text != raw_text else "",
        "section_editor_trace": editor_trace,
        "rewrite_verifier_trace": rewrite_verifier_trace,
        "rewrite_attempt_count": revision_attempts,
        "rewrite_attempt_traces": rewrite_attempt_traces,
        "initial_text": initial_text if revisions else "",
        "text": text,
        "data_dir": str(work_dir),
    }


async def _run(args, report: dict, out_path: Path) -> dict:
    from bootstrap_prompts import bootstrap_world
    import novel_manager
    from novel_presets import STYLE_PRESETS, get_theme_seed

    requested = list(STYLE_PRESETS) if args.styles == "all" else [
        s.strip() for s in args.styles.split(",") if s.strip()
    ]
    unknown = sorted(set(requested) - set(STYLE_PRESETS))
    if unknown:
        raise ValueError(f"unknown styles: {unknown}")
    report.setdefault("metadata", {})["last_run_mode"] = args.mode
    scenarios: list[tuple[str, str, str]] = []
    if args.mode in ("pressure", "both"):
        scenarios += [("pressure", args.pressure_theme, s) for s in requested]
    if args.mode in ("compatible", "both"):
        scenarios += [("compatible", COMPATIBLE_THEME[s], s) for s in requested]

    completed = (
        set()
        if args.force
        else {(r["scenario"], r["style"]) for r in report.get("results", [])}
    )
    base_dirs = report.setdefault("metadata", {}).setdefault("base_dirs", {})
    cost_root = report.setdefault("cost", {})
    cost_root["measurement_version"] = "token-tracker-v1"
    bootstrap_cost = cost_root.setdefault("bootstrap_by_theme", {})
    stamp = int(report["metadata"]["started_at"])
    run_done = 0
    for scenario, theme_key, style_key in scenarios:
        if (scenario, style_key) in completed:
            continue
        base_id = f"styleval_base_{theme_key}_{stamp}"
        # pressure/compatible 若恰好用同一 theme，也共享同一份冷启动。
        base_key = theme_key
        base_dir = Path(base_dirs.get(base_key, "")) if base_dirs.get(base_key) else Path()
        if not base_dirs.get(base_key) or not (base_dir / "tick_state.json").is_file():
            base_dir = Path(novel_manager.get_novel_data_dir("bench", base_id))
            base_dir.mkdir(parents=True, exist_ok=True)
            theme = get_theme_seed(theme_key)
            usage_before = _usage_snapshot()
            started = time.perf_counter()
            await bootstrap_world(
                novel_id=base_id, data_dir=str(base_dir), seed=theme.seed,
                positioning="由后续 style preset 决定", references="无",
                title=f"{theme.label}风格验证",
                cast_a_count=1, cast_b_count=1, cast_c_count=1,
            )
            bootstrap_cost[base_key] = _usage_delta(
                usage_before, _usage_snapshot(), time.perf_counter() - started
            )
            base_dirs[base_key] = str(base_dir)
            _atomic_json(out_path, report)
        # novel_manager contract: id <= 64。长 key（first_person_immersive）必须
        # 先截断；毫秒戳仍保证 crash-resume 不与残留目录碰撞。
        work_id = (
            f"sv_{scenario[:4]}_{style_key[:18]}_{int(time.time() * 1000)}"
        )
        work_dir = Path(novel_manager.get_novel_data_dir("bench", work_id))
        usage_before = _usage_snapshot()
        started = time.perf_counter()
        result = await _generate_one(
            base_dir=base_dir, work_dir=work_dir, style_key=style_key,
            theme_key=theme_key, scenario=scenario, ticks=args.ticks,
            no_judge=args.no_judge, max_revisions=args.max_revisions,
            sequence=args.sequence, section_edit=args.section_edit,
        )
        result["cost"] = _usage_delta(
            usage_before, _usage_snapshot(), time.perf_counter() - started
        )
        if args.force:
            report["results"] = [
                row for row in report.get("results", [])
                if (row.get("scenario"), row.get("style"))
                != (scenario, style_key)
            ]
        report.setdefault("results", []).append(result)
        _atomic_json(out_path, report)
        run_done += 1
        print(
            f"[{run_done}/{len(scenarios)}] {scenario}/{style_key}: "
            f"{'PASS' if result['accepted'] else 'FAIL'} ({result['char_count']} chars)",
            flush=True,
        )
    report["metadata"]["finished_at"] = int(time.time())
    scenario_names = sorted({r.get("scenario", "") for r in report.get("results", [])})
    by_scenario = {
        scenario: {
            "total": sum(r.get("scenario") == scenario for r in report["results"]),
            "passed": sum(
                r.get("scenario") == scenario and bool(r.get("accepted"))
                for r in report["results"]
            ),
        }
        for scenario in scenario_names
        if scenario
    }
    report["metadata"]["modes_present"] = scenario_names
    report["summary"] = {
        "total": len(report.get("results", [])),
        "passed": sum(bool(r.get("accepted")) for r in report.get("results", [])),
        "by_scenario": by_scenario,
    }
    cost_blocks = list(bootstrap_cost.values()) + [
        row["cost"] for row in report.get("results", []) if row.get("cost")
    ]
    cost_root["samples_with_cost"] = sum(
        bool(row.get("cost")) for row in report.get("results", [])
    )
    cost_root["samples_without_cost"] = sum(
        not bool(row.get("cost")) for row in report.get("results", [])
    )
    cost_root["total"] = _aggregate_cost(cost_blocks)
    _atomic_json(out_path, report)
    out_path.with_suffix(".md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-file", default="coding.txt")
    parser.add_argument("--mode", choices=("pressure", "compatible", "both"), default="both")
    parser.add_argument("--pressure-theme", default="apocalypse_wasteland")
    parser.add_argument("--styles", default="all", help="all 或逗号分隔 style keys")
    parser.add_argument("--ticks", type=int, default=1)
    parser.add_argument(
        "--sequence", action="store_true",
        help="多 tick 时投喂显式递进场景，而非重复同一事件",
    )
    parser.add_argument(
        "--section-edit", action="store_true",
        help="多 tick 拼接后运行生产 SectionEditor + 事实验收",
    )
    parser.add_argument(
        "--max-revisions", type=int, choices=(0, 1, 2), default=1,
        help="整节定向修订尝试上限；每次候选必须通过事实守恒复验",
    )
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--resume", default="", help="已有 checkpoint JSON")
    parser.add_argument(
        "--force", action="store_true",
        help="与 --resume 合用，替换所选 scenario/style 的既有结果",
    )
    args = parser.parse_args()
    if args.ticks < 1:
        parser.error("--ticks must be >= 1")

    provider = _configure_provider((ROOT / args.provider_file).resolve())
    from nf_core.llm_client import llm_client
    from nf_core.provider_runtime import stage_provider_scope

    from nf_core.token_budget import TokenBudgetTracker, set_global_tracker

    set_global_tracker(TokenBudgetTracker())
    if args.resume:
        out_path = (ROOT / args.resume).resolve()
        report = json.loads(out_path.read_text(encoding="utf-8"))
    else:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = (
            (ROOT / args.out).resolve() if args.out
            else ROOT / "docs" / "iter" / f"style-validation-{stamp}.json"
        )
        report = {
            "metadata": {
                "started_at": int(time.time()), "git_sha": _git_sha(),
                "provider": provider.diagnostics(),
                "mode": args.mode,
                "ticks": args.ticks,
                "no_judge": args.no_judge, "max_revisions": args.max_revisions,
                "shared_bootstrap": True,
                **_execution_profile(),
            },
            "results": [],
        }
        _atomic_json(out_path, report)
    report.setdefault("metadata", {}).update(_execution_profile())
    async def _execute():
        try:
            return await _run(args, report, out_path)
        finally:
            await llm_client.aclose()

    with stage_provider_scope(provider):
        llm_client.reload(config=provider)
        final = asyncio.run(_execute())
    print(
        f"[DONE] {final['summary']['passed']}/{final['summary']['total']} passed; "
        f"report={out_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
