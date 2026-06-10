"""SafetyFilter — 输出前的内容安全检查。

针对主 Agent 关注问题清单的一项:
* **内容安全与伦理风险** — 在 Narrator 终稿落盘前过滤明显违规模式
  (PII / 极端暴力具体化 / 自我伤害指南类陈述)

设计原则:
* **不依赖 LLM** — 用正则模式 + 类别表, 推理快速、零成本
* **不审查文学张力** — 只阻止"具体可执行的伤害指南"或泄露真实 PII, 不阻止
  虚构暴力、灰色道德、悲剧
* **可拓展** — `SafetyRule` 注册式; 用户可在 deploy 时增删
* **白盒可追溯** — 命中时给出规则 id + 证据片段, 不静默丢弃文本

非目标:
* 不做模型层 jailbreak 防御 (那由 provider 负责)
* 不做版权检测
* 不替代人工审稿
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


Severity = Literal["block", "warn", "log"]


@dataclass(frozen=True)
class SafetyRule:
    rule_id: str
    pattern: re.Pattern[str]
    severity: Severity
    category: str
    description: str


@dataclass
class SafetyHit:
    rule_id: str
    severity: Severity
    category: str
    evidence: str
    location_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "category": self.category,
            "evidence": self.evidence,
            "location_hint": self.location_hint,
        }


@dataclass
class SafetyResult:
    is_blocked: bool = False
    hits: list[SafetyHit] = field(default_factory=list)
    sanitized_text: str = ""  # warn 级可填占位符

    def to_dict(self) -> dict:
        return {
            "is_blocked": self.is_blocked,
            "hits": [h.to_dict() for h in self.hits],
            "sanitized_text": self.sanitized_text,
        }


# ---------------------------------------------------------------------------
# 默认规则集 — 中文场景下的明显违规模式
# ---------------------------------------------------------------------------

# 注意:
# * 默认规则倾向于 block PII 泄露 + 自我伤害"操作指南"
# * 文学暴力 / 灰色道德 / 虚构暴力描写 不进入默认规则
# * 仅匹配明显泄露的格式化 PII (身份证 / 手机号 / 邮箱 / 银行卡)

DEFAULT_RULES: tuple[SafetyRule, ...] = (
    # PII
    SafetyRule(
        rule_id="PII_ID_CARD",
        pattern=re.compile(r"\b\d{17}[\dXx]\b"),
        severity="block",
        category="pii",
        description="疑似中国大陆身份证号",
    ),
    SafetyRule(
        rule_id="PII_PHONE_CN",
        pattern=re.compile(r"\b1[3-9]\d{9}\b"),
        severity="block",
        category="pii",
        description="疑似中国大陆手机号",
    ),
    SafetyRule(
        rule_id="PII_EMAIL",
        pattern=re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        severity="warn",
        category="pii",
        description="邮箱地址",
    ),
    SafetyRule(
        rule_id="PII_BANK_CARD",
        pattern=re.compile(r"\b\d{16,19}\b"),
        severity="warn",
        category="pii",
        description="疑似银行卡号 (16-19 位连续数字)",
    ),
    # 自我伤害"操作指南" — 仅匹配"教学化"陈述, 不阻止角色困境描写
    SafetyRule(
        rule_id="HARM_INSTRUCTION",
        pattern=re.compile(
            r"(具体方法[::]?\s*[1一]|步骤[::]?\s*[1一]).{0,80}?(自杀|自残|服毒|割腕)"
        ),
        severity="block",
        category="harm",
        description="自我伤害操作指南 (具体步骤 + 自伤手段共现)",
    ),
    # 极端违法操作指南
    SafetyRule(
        rule_id="ILLEGAL_BOMB_GUIDE",
        pattern=re.compile(
            r"(制作|合成).{0,30}?(炸弹|爆炸物|甲基苯丙胺|海洛因|冰毒)"
        ),
        severity="block",
        category="illegal",
        description="违禁品制作指南",
    ),
)


# ---------------------------------------------------------------------------
# SafetyFilter
# ---------------------------------------------------------------------------


class SafetyFilter:
    """运行时安全过滤 — block 级命中阻止落盘, warn 级仅记录。"""

    def __init__(self, rules: tuple[SafetyRule, ...] | None = None) -> None:
        self._rules: tuple[SafetyRule, ...] = rules if rules is not None else DEFAULT_RULES

    def check(self, text: str) -> SafetyResult:
        """对 ``text`` 跑全部规则。"""
        if not text:
            return SafetyResult()
        hits: list[SafetyHit] = []
        is_blocked = False
        for rule in self._rules:
            for match in rule.pattern.finditer(text):
                start = match.start()
                evidence = text[max(0, start - 12) : start + 32].replace("\n", " ")
                hits.append(
                    SafetyHit(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        category=rule.category,
                        evidence=f"...{evidence}...",
                        location_hint=f"char_offset={start}",
                    )
                )
                if rule.severity == "block":
                    is_blocked = True
        return SafetyResult(
            is_blocked=is_blocked,
            hits=hits,
            sanitized_text="" if is_blocked else self._mask_warns(text, hits),
        )

    def _mask_warns(self, text: str, hits: list[SafetyHit]) -> str:
        """warn 级命中用规则正则 pattern.sub 打码 (block 不在此处处理)。

        此前用 evidence 上下文片段做 str.replace: 会把命中点前后的无辜文字
        一并替换 (误伤), 且 strip("...") 按字符集剥离会砍掉匹配本体的句点/
        省略号导致漏替。改为直接用产生该 hit 的规则正则替换。
        """
        out = text
        rules_by_id = {r.rule_id: r for r in self._rules}
        masked_rule_ids: set[str] = set()
        for h in hits:
            if h.severity != "warn" or h.rule_id in masked_rule_ids:
                continue
            masked_rule_ids.add(h.rule_id)
            rule = rules_by_id.get(h.rule_id)
            if rule is None:
                continue
            out = rule.pattern.sub(f"[REDACTED-{h.category.upper()}]", out)
        return out

    def add_rule(self, rule: SafetyRule) -> None:
        self._rules = self._rules + (rule,)


__all__ = [
    "SafetyFilter",
    "SafetyRule",
    "SafetyHit",
    "SafetyResult",
    "DEFAULT_RULES",
]
