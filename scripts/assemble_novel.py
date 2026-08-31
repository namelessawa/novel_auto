"""Assemble the three generated chapters into a single novel markdown document.

Reads the E2E report JSON, extracts synopses (titles) and writer prose,
and writes a formatted markdown novel file.

Usage:
    python scripts/assemble_novel.py --report <report.json> --output <novel.md>
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def extract_prose(content: str) -> str:
    """Extract prose from <prose> tags, falling back to raw content."""
    if "<prose>" in content and "</prose>" in content:
        start = content.find("<prose>") + len("<prose>")
        end = content.find("</prose>")
        return content[start:end].strip()
    return content.strip()


def main():
    parser = argparse.ArgumentParser(description="Assemble novel from E2E report")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", type=str, default="测试小说")
    args = parser.parse_args()

    with open(args.report, encoding="utf-8") as f:
        report = json.load(f)

    calls = report["llm_calls"]

    # Extract synopses (chapter titles)
    synopsis_call = next((c for c in calls if c["agent_id"] == "pipeline_synopsis"), None)
    chapter_titles = {}
    if synopsis_call:
        try:
            syn_text = synopsis_call["output"]
            # Strip code fence if present
            syn_text = re.sub(r"^```(?:json)?\s*", "", syn_text.strip())
            syn_text = re.sub(r"\s*```$", "", syn_text.strip())
            syn_data = json.loads(syn_text)
            chapters = syn_data.get("chapters", syn_data if isinstance(syn_data, list) else [])
            for ch in chapters:
                chapter_titles[ch.get("chapter")] = ch.get("title", "")
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"Warning: could not parse synopses: {exc}")

    # Extract writer prose per chapter (in order)
    writer_calls = [c for c in calls if c["agent_id"] == "pipeline_simplified_writer"]
    chapter_prose = []
    for i, wc in enumerate(writer_calls, start=1):
        prose = extract_prose(wc["output"])
        chapter_prose.append((i, prose))

    # Get pacing modes
    pacing_modes = {}
    for c in calls:
        pass  # pacing not in llm_calls; skip

    # Assemble markdown
    lines = []
    lines.append(f"# {args.title}")
    lines.append("")
    lines.append(f"> 生成模型：{report['provider'].get('model', 'unknown')}")
    lines.append(f"> 生成时间：{report.get('completed_at', '')}")
    lines.append(f"> 章节数：{len(chapter_prose)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for chapter_num, prose in chapter_prose:
        title = chapter_titles.get(chapter_num, f"第{chapter_num}章")
        lines.append(f"## 第{chapter_num}章 {title}")
        lines.append("")
        lines.append(prose)
        lines.append("")
        lines.append("---")
        lines.append("")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    total_chars = sum(len(p) for _, p in chapter_prose)
    print(f"Assembled {len(chapter_prose)} chapters, {total_chars} total chars")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
