from __future__ import annotations

import pytest

from agents.section_closer import SectionCloser
from agents.section_editor import SectionEditor
from quality_metrics.section_seams import section_seam_report


def test_section_seam_report_catches_exact_replay() -> None:
    report = section_seam_report([
        "林雪夺回地图，铁门在她身后合拢。她扶起苏默。",
        "林雪夺回地图，铁门在她身后合拢。她扶着苏默继续往城墙走。",
    ])
    assert report.requires_edit is True
    assert any(f.code == "S1_EXACT_SENTENCE_REPLAY" for f in report.findings)


def test_section_seam_report_catches_internal_sentence_replay() -> None:
    report = section_seam_report([
        "城墙还有四百米。林雪继续往前走。城墙还有四百米。"
    ])
    assert report.requires_edit is True
    assert any(f.code == "S0_INTERNAL_SENTENCE_REPLAY" for f in report.findings)


@pytest.mark.asyncio
async def test_fact_verifier_accepts_declared_minimal_state_repair(mock_llm) -> None:
    mock_llm.set_responses([{
        "safe": True,
        "original_contradictions": ["伤腿肿胀后靴筒无法继续藏图"],
        "repaired_contradictions": ["地图存放位置统一为背心内袋"],
        "allowed_repair_changes": ["靴筒改为同一持有者的背心内袋"],
        "residual_contradictions": [],
        "fact_changes": [],
        "causal_changes": [],
        "knowledge_violations": [],
        "reason": "只替换低层存放位置",
    }])

    verdict = await SectionEditor().verify_fact_preservation(
        original="苏莫把地图放进靴筒。后来伤腿肿胀，他又从靴筒取图。",
        candidate="苏莫把地图放进背心内袋。后来伤腿肿胀，他又从内袋取图。",
        protected_terms=["苏莫"],
        declared_repairs=["统一无法使用的藏图位置"],
    )

    assert verdict["safe"] is True
    assert verdict["allowed_repair_changes"]


@pytest.mark.asyncio
async def test_section_editor_adopts_fact_safe_candidate(mock_llm) -> None:
    original = (
        "林雪夺回地图，铁门在她身后合拢。苏默肩上有伤。\n\n"
        "林雪又夺回地图，铁门再次合拢。她扶着苏默向城墙走。"
    ) * 10
    candidate = "".join([
        "林雪夺回地图，铁门在她身后合拢。",
        "苏默肩上有伤，她先用布条压紧伤口。",
        "两人沿积水通道向北移动，没有回头。",
        "地图始终压在林雪怀里，纸角被雨水浸软。",
        "苏默脚步发虚，她便把他的手臂搭到肩上。",
        "远处城墙的灯一盏盏熄灭，路却还没有断。",
        "他们绕过倒塌的泵管，从维修梯爬上地面。",
        "风把警报声吹散，伤口的血仍在往外渗。",
        "林雪重新勒紧布条，确认地图没有遗失。",
        "苏默指向城墙缺口，两人改走更短的排水渠。",
        "守门灯已经近了，铁门则留在他们身后。",
        "她扶着苏默继续走，把下一次选择留到城下。",
        "排水渠里的水没过脚踝，拖慢了两个人的速度。",
        "苏默几次想自己站稳，都被伤腿逼得重新靠回来。",
        "地图外层的油布挡住了雨，里面的墨线仍然清楚。",
        "城下有人举起灯，林雪这才放慢一直没有停过的脚步。",
    ])
    mock_llm.set_responses([
        {
            "final_content": candidate,
            "removed_replays": ["删除第二次夺图与关门"],
            "fact_changes": [],
            "residual_risks": [],
        },
        {
            "safe": True,
            "fact_changes": [],
            "causal_changes": [],
            "knowledge_violations": [],
            "reason": "只删除重复演绎",
        },
    ])
    out = await SectionEditor().edit(
        parts=original.split("\n\n"),
        combined_text=original,
        protected_terms=["林雪", "苏默"],
    )
    assert out.adopted is True
    assert out.final_content == candidate
    assert out.trace["verifier"]["safe"] is True


@pytest.mark.asyncio
async def test_section_editor_rejects_semantic_fact_change(mock_llm) -> None:
    original = (
        "林雪带着受伤的苏默离开泵房。地图在林雪手里。\n\n"
        "两人抵达城墙，林雪仍拿着地图。"
    ) * 12
    candidate = (
        "林雪独自抵达城墙。苏默已经死在泵房，地图落入敌人手中。"
    ) * 12
    mock_llm.set_responses([
        {
            "final_content": candidate,
            "removed_replays": [],
            "fact_changes": [],
            "residual_risks": [],
        },
        {
            "safe": False,
            "fact_changes": ["新增苏默死亡并改变地图归属"],
            "causal_changes": [],
            "knowledge_violations": [],
            "reason": "事实改变",
        },
    ])
    out = await SectionEditor().edit(
        parts=original.split("\n\n"),
        combined_text=original,
        protected_terms=[],
    )
    assert out.adopted is False
    assert out.final_content == original
    assert out.trace["reject_reason"] == "semantic_fact_guard_failed"


@pytest.mark.asyncio
async def test_section_editor_repairs_unmotivated_injury_transfer(mock_llm) -> None:
    part1 = "".join([
        "苏默左手按着右肋，血从指缝渗出。",
        "林雪扶着他离开泵房，地图由她收在腰带里。",
        "两人绕过过滤罐，来到东南角的通风井。",
        "苏默每走一步都会停一下，右侧工装已经湿透。",
        "林雪没有受伤，只是掌心沾了闸门上的铁锈。",
        "她先把地图塞紧，才动手抬起沉重的井盖。",
        "苏默侧身钻入狭窄入口，呼吸声被铁壁放大。",
        "林雪跟着下去，仍由她保管那张路线图。",
        "井盖落下前，苏默的伤口又滴了一串血。",
        "黑暗吞掉最后一道光，两人继续往井底移动。",
        "爬梯上的锈屑不断脱落，打在苏默染血的肩侧。",
        "林雪走在下面接应，腰间地图始终没有离身。",
    ])
    part2 = "".join([
        "下到井底后，积水已经没过两人的脚踝。",
        "林雪肋下的血还在往外渗，布料贴住皮肤。",
        "苏默打开手电，先照向墙后的水泵。",
        "地图仍在林雪腰间，没有发生过交接。",
        "她展开纸面，确认南侧路线只剩半截。",
        "苏默靠着井壁喘气，问她还能认出多少。",
        "水泵突然变调，积水向两边荡开细纹。",
        "林雪收好地图，决定先寻找另一处出口。",
        "苏默没有反对，只把手电转向通道深处。",
        "他们离开原地时，身后仍响着沉闷嗡鸣。",
        "通道越往前越窄，苏默只得压住右肋侧身通过。",
        "林雪在前方清理碎石，地图边角蹭到潮湿墙面。",
    ])
    original = part1 + "\n\n" + part2
    candidate = original.replace("林雪肋下的血", "苏默肋下的血")
    mock_llm.set_responses([
        {
            "final_content": candidate,
            "removed_replays": [],
            "continuity_repairs": ["恢复前段已确立的苏默右肋伤"],
            "fact_changes": [],
            "residual_risks": [],
        },
        {
            "safe": True,
            "original_contradictions": ["伤势从苏默无依据转移给林雪"],
            "repaired_contradictions": ["后段恢复为苏默肋伤"],
            "residual_contradictions": [],
            "fact_changes": [],
            "causal_changes": [],
            "knowledge_violations": [],
            "reason": "修复的是原稿漂移",
        },
    ])
    out = await SectionEditor().edit(
        parts=[part1, part2],
        combined_text=original,
        protected_terms=["林雪", "苏默"],
    )
    assert out.adopted is True
    assert "林雪肋下的血" not in out.final_content
    assert out.trace["continuity_repairs"]
    assert out.trace["verifier"]["repaired_contradictions"]


@pytest.mark.asyncio
async def test_section_editor_repairs_consumed_resource_reappearance(mock_llm) -> None:
    part1 = "".join([
        "苏默从口袋里拿出仅剩的三片净水片。",
        "林雪把三片全部碾成粉末，敷进他的伤口。",
        "白色药粉很快被黑血浸透，再也无法回收。",
        "她用纱布缠紧小腿，扶着苏默站起来。",
        "两个人离开废车，向城墙下的阴影移动。",
        "苏默问还剩多少，林雪摊开空空的手掌。",
        "风把包装纸卷走，袋里已经没有净水片。",
        "他们只能用空水壶换取下一道门的通行。",
        "林雪把背包倒过来抖了两次，除了纱布再没有其他东西。",
        "苏默看见空袋，没有再问那三片净水片的下落。",
        "远处的城门亮着一盏白灯，灯下排队的人都抱着自己的交换物。",
        "两人每走一段就要停下，免得纱布下的伤口再次裂开。",
    ])
    part2 = "".join([
        "守门人拦在甬道入口，先检查两人的行囊。",
        "林雪伸手进袋，摸到苏默剩下的三片净水片。",
        "她准备把它们交出去，换苏默进入医务室。",
        "苏默靠着墙，受伤的小腿仍被纱布裹紧。",
        "门后的担架已经推来，轮子压过碎石。",
        "守门人摊开手，等她付清这笔入门费用。",
        "城墙上的探照灯转过来，照亮空水壶。",
        "林雪没有别的物资，只能重新检查背包。",
        "哨塔上传来铁链拖动的声音，入口开始缓慢收紧。",
        "担架停在门线后，守门人仍等着一件可以兑换的物资。",
        "林雪听见医务室里有人催促，却只能继续摊着没有任何药片的手。",
        "苏默把空水壶放到地上，等守门人决定这件破东西能否抵账。",
    ])
    original = part1 + "\n\n" + part2
    candidate = original.replace(
        "林雪伸手进袋，摸到苏默剩下的三片净水片。",
        "林雪伸手进袋，只摸到那张被揉皱的包装纸。",
    ).replace(
        "她准备把它们交出去，换苏默进入医务室。",
        "她只能把空水壶递出去，试着换苏默进入医务室。",
    )
    mock_llm.set_responses([
        {
            "final_content": candidate,
            "removed_replays": [],
            "continuity_repairs": ["删除三片净水片消耗后无故恢复的数量漂移"],
            "fact_changes": [],
            "residual_risks": [],
        },
        {
            "safe": True,
            "original_contradictions": ["三片净水片全部用完后又恢复为三片"],
            "repaired_contradictions": ["后段保持净水片为零"],
            "residual_contradictions": [],
            "fact_changes": [],
            "causal_changes": [],
            "knowledge_violations": [],
            "reason": "候选恢复了明确的资源消耗结果",
        },
    ])
    out = await SectionEditor().edit(
        parts=[part1, part2],
        combined_text=original,
        protected_terms=["林雪", "苏默"],
    )
    assert out.adopted is True
    assert "剩下的三片净水片" not in out.final_content
    assert out.trace["verifier"]["original_contradictions"]


@pytest.mark.asyncio
async def test_section_editor_retries_with_verifier_contradictions(mock_llm) -> None:
    part1 = (
        "林雪把地图收进内袋，纸面仍然完整，路线由她保管；"
        + "她沿着干燥的检修道向南前进，每个岔口都核对标记；" * 8
        + "抵达排水口时，地图依然在林雪的内袋里。"
    )
    part2 = (
        "离开排水口后，苏默从自己的口袋里取出那张地图；"
        + "他们继续沿城墙外侧移动，脚下的碎石不断滑落；" * 8
        + "林雪在前方探路，全程没有与苏默发生地图交接。"
    )
    original = part1 + "\n\n" + part2
    repaired = original.replace(
        "苏默从自己的口袋里取出那张地图",
        "林雪从自己的内袋里取出那张地图",
    )
    mock_llm.set_responses([
        {
            "final_content": original,
            "removed_replays": [],
            "continuity_repairs": [],
            "fact_changes": [],
            "residual_risks": [],
        },
        {
            "safe": False,
            "original_contradictions": ["地图无交接却从林雪转到苏默"],
            "repaired_contradictions": [],
            "residual_contradictions": ["地图归属漂移"],
            "fact_changes": [],
            "causal_changes": [],
            "knowledge_violations": [],
            "reason": "候选未修复原稿矛盾",
        },
        {
            "final_content": repaired,
            "continuity_repairs": ["恢复地图由林雪持有"],
            "fact_changes": [],
        },
        {
            "safe": True,
            "original_contradictions": ["地图无交接却从林雪转到苏默"],
            "repaired_contradictions": ["后段恢复为林雪从内袋取图"],
            "residual_contradictions": [],
            "fact_changes": [],
            "causal_changes": [],
            "knowledge_violations": [],
            "reason": "只修复了归属漂移",
        },
    ])
    out = await SectionEditor().edit(
        parts=[part1, part2],
        combined_text=original,
        protected_terms=["林雪", "苏默"],
    )
    assert out.adopted is True
    assert "苏默从自己的口袋里取出" not in out.final_content
    assert out.trace["repair_attempted"] is True
    assert out.trace["repair_verifier"]["safe"] is True


@pytest.mark.asyncio
async def test_section_closer_runs_editor_before_title(monkeypatch, mock_llm) -> None:
    monkeypatch.setenv("SECTION_EDITOR_ENABLE", "1")
    monkeypatch.setenv("SECTION_EDITOR_VERIFY_ENABLE", "1")
    parts = [
        "林雪夺回地图，带着苏默离开泵房。" * 15,
        "林雪不再回头，扶着苏默抵达城墙。" * 15,
    ]
    edited = ("林雪夺回地图后，扶着受伤的苏默继续向城墙前进，" * 18) + "两人终于抵达门下。"
    mock_llm.set_responses([
        {
            "final_content": edited,
            "removed_replays": [],
            "fact_changes": [],
            "residual_risks": [],
        },
        {
            "safe": True,
            "fact_changes": [],
            "causal_changes": [],
            "knowledge_violations": [],
            "reason": "事实守恒",
        },
        "雨夜入城",
    ])
    out = await SectionCloser().close_section(
        narrative_text="\n\n".join(parts),
        narrative_parts=parts,
        silent_ticks=[],
        chapter=1,
        section_no=1,
        protected_terms=["林雪", "苏默"],
    )
    assert out.final_content == edited
    assert out.editor_trace["adopted"] is True
    assert out.title == "雨夜入城"
    assert len(mock_llm.calls) == 3
