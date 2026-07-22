"""用真实 OpenAI-compatible provider 生成多风格同场景对照报告。

报告逐项保留完整 system/user prompt 与首轮原始输出，同时记录 StylePreset
版本、哈希、token usage 和确定性风格契约检查。provider 文件只用于进程内
配置，API key 永不写入 JSON/Markdown。

示例：
  python scripts/run_style_generation_report.py --provider-file coding.txt
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "scripts")]


DEFAULT_STYLES = (
    "literary",
    "noir_cold",
    "hot_blooded",
    "warm_healing",
    "classical_chapter",
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "iter"
    / f"style-generation-samples-{datetime.now():%Y%m%d}.json"
)

SYSTEM_PROMPT = """\
你是一名成熟的中文长篇小说作家。把用户给出的固定场景事实写成一个完整、连续、可直接进入小说正文的片段。

硬约束：
1. 事实优先于风格；风格只能改变叙述方式，不得改写人物、关系、因果与结局。
2. 正文控制在 900—1200 个中文字符左右，允许少量浮动，但必须写完指定事件链。
3. 只输出小说正文，不要标题、前言、解释、分析、Markdown 围栏或 JSON。
4. 不新增命名人物、超自然设定、死亡、打斗或场景外支线。
5. 结尾必须落实两人的选择和开门动作，不得停在“是否开门”的悬念上。
"""

SCENE_FACTS = """\
【固定场景】
- 地点与时间：架空旧港城，暴雨刚停的凌晨；旧灯塔顶层，天亮前。
- 人物：沈砚与林秋，多年来共同维护灯塔，习惯以行动而非长篇表白关照彼此。
- 起点：灯罩玻璃裂了，沈砚正在修灯；林秋从旧抽屉夹层取出一封发黄的信，手掌被玻璃划出一道浅口。
- 信中事实：十二年前那场港难前，港务处确实收到过风暴警告，却有人压下警告；存档签字与林秋家族有关。这封信是能交给调查员的实证。
- 外部压力：调查员已到灯塔门外，按约敲门；若天亮前不交信，旧港改造将拆除档案室，线索会永久断掉。
- 互动与推进：沈砚先替林秋清理并包扎伤口；两人围绕“保护眼前的人”与“让旧事见光”发生一次克制但明确的分歧，随后达成共同选择。
- 固定结局：两人决定把信交给调查员。沈砚拿着信，林秋亲手拉开灯塔门；修好的灯在他们身后重新亮起。
- 禁止改写：不得把信烧掉、藏起或伪造；不得让调查员离开；不得改成拒绝交信；不得新增幕后真凶身份或替十二年前事件定案。
"""


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def _build_user_prompt(preset: Any) -> str:
    return f"""\
【本次风格】
- key：{preset.key}
- 名称：{preset.label}
- 说明：{preset.description}

【完整风格契约】
{preset.narrator_addendum.rstrip()}

【交稿前短清单】
{preset.final_checklist}

【冲突处理】
{preset.conflict_policy}

{SCENE_FACTS}

请严格按上述风格重述同一事件链。现在只输出完整小说正文。
"""


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)


def _fenced(text: str, language: str = "text") -> str:
    longest = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    fence = "`" * max(4, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def _report_markdown(report: dict[str, Any]) -> str:
    metadata = report["metadata"]
    usage = report["summary"]["usage"]
    lines = [
        "# 多风格同场景真实生成测试报告",
        "",
        "> 本报告记录模型首轮原始结果；未使用 LLM judge，也未对失败项自动改写。",
        "",
        "## 测试概览",
        "",
        f"- 生成时间：`{metadata['generated_at']}`",
        f"- Git 分支 / 提交：`{metadata['git_branch']}` / `{metadata['git_sha']}`",
        f"- Provider / 模型：`{metadata['provider']['provider']}` / "
        f"`{metadata['provider']['model']}`",
        f"- API 地址：`{metadata['provider']['base_url']}`",
        f"- 样本：`{report['summary']['successful']}/{report['summary']['requested']}` 成功",
        f"- Token：prompt `{usage['prompt_tokens']}` + completion "
        f"`{usage['completion_tokens']}` = `{usage['total_tokens']}`",
        f"- 凭据：从 `{metadata['provider']['source_file']}` 读取，仅用于调用，"
        "未写入报告",
        "- 生成策略：同一固定场景，每个风格各调用一次；temperature "
        f"`{metadata['request_defaults']['temperature']}`，max_tokens "
        f"`{metadata['request_defaults']['max_tokens']}`",
        "",
        "## 结果索引",
        "",
        "| 风格 | 输出字符 | 耗时 | Token | 确定性检查 |",
        "|---|---:|---:|---:|---|",
    ]
    for result in report["results"]:
        if result.get("error"):
            lines.append(
                f"| `{result['style_key']}` | - | - | - | 调用失败 |"
            )
            continue
        det = result["deterministic_check"]
        verdict = "通过" if det["passed"] else "有发现项"
        lines.append(
            f"| `{result['style_key']}` {result['style_label']} | "
            f"{result['output']['char_count']} | {result['response']['latency_sec']}s | "
            f"{result['response']['usage']['total_tokens']} | {verdict} |"
        )

    lines.extend(
        [
            "",
            "## 完整输入与输出",
            "",
            "以下内容按真实调用顺序排列。每节都完整列出发送给模型的两条消息，"
            "以及应用层收到的完整正文。",
            "",
        ]
    )
    for index, result in enumerate(report["results"], start=1):
        lines.extend(
            [
                f"### {index}. {result['style_label']} (`{result['style_key']}`)",
                "",
                f"- Preset 版本：`{result['preset']['version']}`",
                f"- Prompt hash：`{result['preset']['prompt_hash']}`",
            ]
        )
        if result.get("error"):
            lines.extend([f"- 调用错误：`{result['error']}`", ""])
            continue
        lines.extend(
            [
                f"- 输出 SHA-256：`{result['output']['sha256']}`",
                f"- 响应耗时：`{result['response']['latency_sec']}s`",
                "",
                "#### 完整 system prompt",
                "",
                _fenced(result["request"]["system_prompt"]),
                "",
                "#### 完整 user prompt",
                "",
                _fenced(result["request"]["user_prompt"]),
                "",
                "#### 完整原始输出",
                "",
                _fenced(result["output"]["text"]),
                "",
                "#### 确定性风格契约检查",
                "",
                _fenced(
                    json.dumps(
                        result["deterministic_check"],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "json",
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## 说明与边界",
            "",
            "- `passed` 只代表仓库现有字面规则未发现问题，不等同于文学质量评分。",
            "- 报告保留首轮输出，便于观察各 preset 在相同剧情约束下的自然表现。",
            "- JSON 是机器可读的权威记录，Markdown 是其完整可读展开。",
            "",
        ]
    )
    return "\n".join(lines)


def _safe_error(exc: Exception) -> str:
    """Avoid persisting provider error bodies that might echo credentials."""
    return f"{type(exc).__name__}: generation failed; see console logs"


def _assert_secret_absent(*payloads: str) -> None:
    secret = os.environ.get("CUSTOM_API_KEY", "")
    if secret and any(secret in payload for payload in payloads):
        raise RuntimeError("credential leak guard rejected report payload")


def _checkpoint(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    markdown_text = _report_markdown(report)
    _assert_secret_absent(json_text, markdown_text)
    _atomic_write(json_path, json_text)
    _atomic_write(markdown_path, markdown_text)


async def _generate(
    *,
    styles: list[str],
    provider: dict[str, Any],
    json_path: Path,
    markdown_path: Path,
    temperature: float,
    max_tokens: int,
    retries: int,
) -> dict[str, Any]:
    from nf_core.llm_client import llm_client
    from novel_presets.style_presets import get_style_preset
    from quality_metrics.style_contract import style_contract_report

    safe_provider = {
        "provider": provider["provider"],
        "base_url": provider["base_url"],
        "model": provider["model"],
        "source_file": Path(provider["source_file"]).name,
        "credential_present": bool(provider["credential_present"]),
        "credential_persisted": False,
    }
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "metadata": {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "git_branch": _git_output("branch", "--show-current"),
            "git_sha": _git_output("rev-parse", "HEAD"),
            "provider": safe_provider,
            "request_defaults": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "single_pass": True,
                "llm_judge": False,
                "automatic_rewrite": False,
            },
            "scene_design": "same facts; only StylePreset contract changes",
        },
        "summary": {
            "requested": len(styles),
            "successful": 0,
            "failed": 0,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "total_tokens": 0,
            },
        },
        "results": [],
    }

    for index, style_key in enumerate(styles, start=1):
        preset = get_style_preset(style_key)
        user_prompt = _build_user_prompt(preset)
        print(
            f"[{index}/{len(styles)}] generating {style_key} ({preset.label})...",
            flush=True,
        )
        response = None
        started = time.perf_counter()
        error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = await llm_client.chat(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    agent_id=f"style_report_{style_key}",
                    priority="critical",
                    tick=index,
                )
                if not response.content.strip():
                    raise ValueError("provider returned empty content")
                error = None
                break
            except Exception as exc:  # keep other styles independently testable
                error = exc
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
        latency = round(time.perf_counter() - started, 3)
        result: dict[str, Any] = {
            "style_key": preset.key,
            "style_label": preset.label,
            "style_description": preset.description,
            "preset": {
                "version": preset.version,
                "prompt_hash": preset.prompt_hash,
                "det_rules": list(preset.det_rules),
            },
            "request": {
                "system_prompt": SYSTEM_PROMPT,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        }
        if response is None:
            assert error is not None
            result["error"] = _safe_error(error)
            report["summary"]["failed"] += 1
            print(f"  failed: {type(error).__name__}", flush=True)
        else:
            text = response.content
            usage = {
                "prompt_tokens": int(response.usage_prompt_tokens),
                "completion_tokens": int(response.usage_completion_tokens),
                "cached_tokens": int(response.usage_cached_tokens),
            }
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
            det_report = style_contract_report(
                preset.key, text, preset.det_rules, strict=True
            ).to_dict()
            result.update(
                {
                    "response": {"latency_sec": latency, "usage": usage},
                    "output": {
                        "text": text,
                        "char_count": len(text),
                        "non_whitespace_char_count": len("".join(text.split())),
                        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    },
                    "deterministic_check": det_report,
                }
            )
            report["summary"]["successful"] += 1
            for key in ("prompt_tokens", "completion_tokens", "cached_tokens"):
                report["summary"]["usage"][key] += usage[key]
            report["summary"]["usage"]["total_tokens"] += usage["total_tokens"]
            print(
                f"  ok: {len(text)} chars, {usage['total_tokens']} tokens, "
                f"det_pass={det_report['passed']}",
                flush=True,
            )
        report["results"].append(result)
        _checkpoint(report, json_path, markdown_path)

    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-file", type=Path, default=ROOT / "coding.txt")
    parser.add_argument(
        "--styles",
        default=",".join(DEFAULT_STYLES),
        help="comma-separated StylePreset keys",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--temperature", type=float, default=0.72)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--retries", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    from validate_styles import _configure_provider

    provider = _configure_provider(args.provider_file.resolve())
    styles = [item.strip() for item in args.styles.split(",") if item.strip()]
    if not styles:
        raise ValueError("at least one style is required")
    json_path = args.out.resolve()
    if json_path.suffix.lower() != ".json":
        raise ValueError("--out must use a .json suffix")
    markdown_path = json_path.with_suffix(".md")
    report = asyncio.run(
        _generate(
            styles=styles,
            provider=provider,
            json_path=json_path,
            markdown_path=markdown_path,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            retries=max(0, args.retries),
        )
    )
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
