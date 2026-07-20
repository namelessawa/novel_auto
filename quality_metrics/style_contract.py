"""风格 preset 的零成本、可复现验收层。

只把字面可证的违约标为 high 并触发 production 一次定向重写；需要审美判断
的项目保留为 medium，交给验证脚本的语义 judge，避免把启发式误当事实。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StyleContractFinding:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StyleContractReport:
    style_key: str
    strict: bool
    checked_rules: tuple[str, ...]
    findings: tuple[StyleContractFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def requires_rewrite(self) -> bool:
        return any(f.severity == "high" for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "style_key": self.style_key,
            "strict": self.strict,
            "checked_rules": list(self.checked_rules),
            "passed": self.passed,
            "requires_rewrite": self.requires_rewrite,
            "findings": [f.to_dict() for f in self.findings],
        }


_META_MARKERS = (
    "首先，理解任务", "首先,理解任务", "从素材看", "关键点包括",
    "作为AI", "作为 AI", "narrative_text", "style_diagnostics",
)
_STANDALONE_WRAPPER = re.compile(
    r"(?im)^\s*(?:```(?:text|markdown|json)?|text|markdown)\s*$"
)
_WRAPPER_PREFIX = re.compile(
    r"(?im)^\s*(?:text|markdown|other|ther)(?=[\u3400-\u9fff])"
)
_CAMERA_META = (
    "镜头推向", "镜头跟随", "镜头切到", "镜头切向", "特写镜头",
    "画面定格", "摄影机", "摄像机", "全景，", "中景，", "近景，",
    "景别：", "景别:",
)
_ACTIVE_ENDING = re.compile(
    r"(冲|扑|抓|拔|举|砸|撞|推|拉|跃|追|迎|踏|劈|刺|扣|握|奔|闯|出手|开火|瞄准|喊|喝)[^。！？]{0,18}[。！？]?$"
)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?]+", text) if s.strip()]


def style_contract_report(
    style_key: str,
    text: str,
    rules: tuple[str, ...] | list[str],
    *,
    strict: bool,
) -> StyleContractReport:
    findings: list[StyleContractFinding] = []
    paragraphs = _paragraphs(text)
    sentences = _sentences(text)

    def add(code: str, severity: str, message: str) -> None:
        findings.append(StyleContractFinding(code, severity, message))

    for rule in rules:
        if rule == "no_meta_leak":
            hit = next((m for m in _META_MARKERS if m in text), "")
            if hit:
                add(rule, "high", f"正文含生成元语言 {hit!r}")
            elif match := _STANDALONE_WRAPPER.search(text):
                add(rule, "high", f"正文含格式包装残片 {match.group(0).strip()!r}")
            elif match := _WRAPPER_PREFIX.search(text):
                add(rule, "high", f"正文含行首格式包装残片 {match.group(0).strip()!r}")
        elif rule == "no_camera_meta":
            hit = next((m for m in _CAMERA_META if m in text), "")
            if hit:
                add(rule, "high", f"正文含摄影指令 {hit!r}")
        elif rule == "no_exclamation":
            if "！" in text or "!" in text:
                add(rule, "high", "冷峻风格正文出现感叹号")
        elif rule == "first_person":
            if not re.search(r"(^|[“‘，。！？\s])我(?!们)", text):
                add(rule, "high", "第一人称契约下正文没有可辨认的“我”视点")
        elif rule == "active_ending" and strict:
            tail = text[-90:].strip()
            if not _ACTIVE_ENDING.search(tail):
                add(rule, "medium", "严格节拍未以人物动作/出手收尾")
        elif rule == "hot_blooded_observables" and strict:
            if "！" not in text and "!" not in text:
                add(rule, "high", "严格热血节拍缺少至少一个感叹号")
            if not re.search(r"[“‘][^”’]{0,60}(我要|来吧|绝不|不能|一起|上|冲|战)[^”’]{0,40}[”’]", text):
                add(rule, "medium", "未检出角色说出口的誓言或挑战")
        elif rule == "somber_structure" and strict:
            if not 3 <= len(paragraphs) <= 5:
                add(rule, "high", f"沉郁严格节拍应为3-5段，实际{len(paragraphs)}段")
            longest = max((len(s) for s in sentences), default=0)
            if longest > 300:
                add(rule, "high", f"存在{longest}字无句号 run-on")
            elif longest > 120:
                add(rule, "medium", f"最长单句{longest}字，超过建议120字")
        elif rule == "warm_safety":
            hit = next(
                (m for m in ("尸体", "死亡倒计时", "伤害过程", "断肢", "开膛", "三天后会死") if m in text),
                "",
            )
            if hit:
                add(rule, "high", f"治愈风格前景化禁区内容 {hit!r}")
        elif rule == "black_humor_originality":
            copied_logic = re.search(
                r"(?:规章|表格|制度|流程).{0,6}不会饿[，,；;].{0,16}(?:执行|填|办|人).{0,6}会",
                text,
            )
            copied_injury = re.search(
                r"(?:规章|规程|表格|制度|流程).{0,8}不会(?:饿|失血|受伤|死)",
                text,
            )
            if (
                copied_logic
                or copied_injury
                or "规章当然不会饿，执行规章的人会" in text
            ):
                add(
                    rule,
                    "high",
                    "干冷旁白复刻了契约示例的“制度不饿/人会饿”句式",
                )
        elif rule == "classical_markers" and strict:
            first = text.lstrip("\ufeff \n")
            if not first.startswith(("却说", "且说")):
                add(rule, "high", "章回严格节拍首句未以“却说/且说”起")
            marker_groups = [
                ("原来",), ("遂",), ("便",), ("乃",), ("但见",),
                ("正是",), ("却闻",), ("只见",),
            ]
            distinct = sum(any(m in text for m in group) for group in marker_groups)
            if distinct < 4:
                add(rule, "high", f"章回标记仅检出{distinct}种，少于4种")
            last_p = paragraphs[-1] if paragraphs else ""
            if not last_p.startswith(("正是", "却闻", "只见")):
                add(rule, "high", "末段未以“正是/却闻/只见”之一领起")
        elif rule == "short_paragraphs":
            if paragraphs and max(len(p) for p in paragraphs) > 300:
                add(rule, "medium", "口语轻读风格出现超过300字的长段")
        elif rule == "character_presence":
            # 没有角色名单时只能报弱信号，不据此自动重写。
            if paragraphs and not re.search(r"[他她我你]|[“”‘’]", text):
                add(rule, "medium", "正文未检出人物代词或对白，可能退化为纯环境")

    return StyleContractReport(
        style_key=style_key,
        strict=strict,
        checked_rules=tuple(rules),
        findings=tuple(findings),
    )
