"""LLM 输出 → JSON 的统一解析管道 (v2.34 强化)。

历史: v2.19.6 抽出 ``strip_code_fence`` 把 8 处 markdown 围栏剥离统一到一处.
本次 (v2.34): MiMo 等 reasoning 模型经常:

1. 把 reasoning chain 当 content 返回 → 文本完全不是 JSON
2. 在 JSON 字符串里塞未转义的 ``"`` / 字面换行 / 尾随逗号
   → 严格 json.loads 在所有 11 agent 站点炸成一片

把鲁棒 ``extract_json_object`` + ``parse_llm_json`` 上提到这里, 增加
``json_repair`` 兜底, 所有 agent / bootstrap 共用同一个解析入口.

API:
* :func:`strip_code_fence` — 历史接口, 仅剥首尾 ``` fence
* :func:`extract_json_object` — 深度平衡扫描第一个 ``{...}`` 子串
* :func:`parse_llm_json` — 完整管道 (strip + extract + json.loads + json_repair 兜底)

解析策略 (parse_llm_json):
1. strip_code_fence + extract_json_object 拿到候选子串
2. 先 json.loads — 干净 JSON 走 fast path (绝大多数 agent 输出)
3. 失败时降级 json_repair — 修复未转义引号 / 字面换行 / 尾随逗号 / 缺逗号
4. 两层都失败 raise 原 ``json.JSONDecodeError``, 调用方既有 try/except 兜底不动
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# json_repair 兜底脏 JSON. 缺包时降级为只走 json.loads (向后兼容旧镜像).
try:
    from json_repair import repair_json as _repair_json
except ImportError:  # pragma: no cover — Docker 镜像未 rebuild 时降级
    logger.warning(
        "json_repair not installed; parse_llm_json will only use stdlib json.loads. "
        "Install with: pip install json-repair>=0.45.0"
    )
    _repair_json = None  # type: ignore[assignment]


def strip_code_fence(text: str) -> str:
    """剥离 LLM 常见的 markdown 围栏。

    行为:
    * 先 strip 前后空白
    * 若整体以 ``` 开头 → 去掉第一行 (含可能的 ``json`` / ``yaml`` 语言标签)
    * 末行 strip 后仍以 ``` 开头 → 同时去掉
    * 否则原样返回

    空字符串 / 仅空白安全返回 ``""``。

    NOTE: 仅处理整体被 fence 包围的常见 case; prose + fence 混合时仍可能返回
    未被剥净的内容. 配合 :func:`extract_json_object` 一起使用更鲁棒.
    """
    t = text.strip()
    if not t:
        return ""
    if t.startswith("```"):
        lines = t.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t


def extract_json_object(text: str) -> str:
    """从 LLM 输出中提取第一个深度平衡的 ``{...}`` 子串。

    reasoning 模型常在 JSON 前后塞散文 / markdown / 注释; "严格 JSON,
    不要 markdown 代码块" 在 prompt 里只是约定不是约束. 实际输出形式:

        Here is the JSON:
        ```json
        {...}
        ```
        Done.

    本函数从第一个 ``{`` 开始, 扫描到深度归零的对应 ``}`` 返回该子串.
    字符串字面量内的 ``{}`` 与转义引号正确处理. 没找到 ``{`` 时原样返回
    (让上游 ``json.loads`` 报清晰的 "Expecting value" 错误, 而不是返回 "").
    """
    start = text.find("{")
    if start < 0:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def parse_llm_json(raw: str) -> dict:
    """LLM 原始输出 → dict 的标准入口。

    管道:
    1. :func:`strip_code_fence` — 剥首尾 markdown 围栏
    2. :func:`extract_json_object` — 提取第一个平衡 ``{...}`` 子串 (跳过前后散文)
    3. ``json.loads`` (fast path, 干净 JSON 直接出结果)
    4. 失败时 ``json_repair`` 兜底 (修复未转义引号 / 字面换行 / 尾随逗号 / 缺逗号 / ...)
    5. 都失败 raise 原 ``json.JSONDecodeError``

    本模块**故意不打日志** —— raw 的语义只有调用方知道 (agent_id / stage /
    character_id ...). 调用方应在 except 分支记录 ``raw[:N]`` 用于诊断.

    返回:
        解析后的 dict (顶层 JSON 对象).

    Raises:
        json.JSONDecodeError: 当输出不是有效 JSON 对象且 json_repair 也无法修复时.
    """
    text = strip_code_fence(raw)
    text = extract_json_object(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if _repair_json is None:
            raise
        # json_repair 容错: 未转义引号 / 字面换行 / 单引号 / 尾随逗号 / 缺逗号.
        # 注意它 *几乎不抛错* — 修不出就吐 {} 或 []. 因此返回非 dict 时仍要
        # raise 原 json.JSONDecodeError, 让调用方走 fallback 而不是误吃空对象.
        try:
            repaired = _repair_json(text, return_objects=True)
        except Exception:
            raise e from None
        if isinstance(repaired, dict):
            return repaired
        # 顶层 [] 或 标量 — 调用方期望 dict, 视作解析失败
        raise e from None


__all__ = ["strip_code_fence", "extract_json_object", "parse_llm_json"]
