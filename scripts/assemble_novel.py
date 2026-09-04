"""Assemble generated chapters into a single novel markdown document.

Two sources (in priority order):
  1. --data-dir: reads pipeline/prose_ch{N}.md + synopsis_ch{N}.json from a
     novel data directory (works across resumed runs).
  2. --report: extracts writer prose and synopses from an E2E report JSON.

Usage:
    python scripts/assemble_novel.py --data-dir <novel_data> --output <novel.md>
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


def collect_from_data_dir(data_dir: Path) -> tuple[dict[int, str], dict[int, str]]:
    """Return (chapter_prose, chapter_titles) from pipeline data files."""
    pipeline_dir = data_dir / "pipeline"
    prose: dict[int, str] = {}
    titles: dict[int, str] = {}

    for path in sorted(pipeline_dir.glob("prose_ch*.md")):
        match = re.match(r"prose_ch(\d+)\.md", path.name)
        if match:
            prose[int(match.group(1))] = path.read_text(encoding="utf-8").strip()

    for path in sorted(pipeline_dir.glob("synopsis_ch*.json")):
        match = re.match(r"synopsis_ch(\d+)\.json", path.name)
        if not match:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            title = data.get("title", "")
            if title:
                titles[int(match.group(1))] = title
        except (json.JSONDecodeError, OSError):
            continue

    return prose, titles


def collect_from_report(report_path: Path) -> tuple[dict[int, str], dict[int, str]]:
    """Return (chapter_prose, chapter_titles) from an E2E report JSON."""
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    calls = report["llm_calls"]
    titles: dict[int, str] = {}

    synopsis_call = next((c for c in calls if c["agent_id"] == "pipeline_synopsis"), None)
    if synopsis_call:
        try:
            syn_text = synopsis_call["output"]
            syn_text = re.sub(r"^```(?:json)?\s*", "", syn_text.strip())
            syn_text = re.sub(r"\s*```$", "", syn_text.strip())
            syn_data = json.loads(syn_text)
            chapters = syn_data.get("chapters", syn_data if isinstance(syn_data, list) else [])
            for ch in chapters:
                if ch.get("title"):
                    titles[ch.get("chapter")] = ch.get("title", "")
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"Warning: could not parse synopses: {exc}")

    states = [
        s for s in report.get("pipeline_states", [])
        if s.get("phase") == "chapter_completed"
    ]
    completed = [s["chapter"] for s in states]
    writer_calls = [c for c in calls if c["agent_id"] == "pipeline_simplified_writer"]

    prose: dict[int, str] = {}
    for idx, wc in enumerate(writer_calls):
        chapter = completed[idx] if idx < len(completed) else idx + 1
        text = extract_prose(wc["output"])
        if text:
            prose[chapter] = text

    return prose, titles


def main():
    parser = argparse.ArgumentParser(description="Assemble novel from pipeline data")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="Novel data dir containing pipeline/prose_ch*.md")
    parser.add_argument("--report", type=Path, default=None,
                        help="E2E report JSON (fallback source)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", type=str, default="测试小说")
    args = parser.parse_args()

    if not args.data_dir and not args.report:
        parser.error("either --data-dir or --report is required")

    prose: dict[int, str] = {}
    titles: dict[int, str] = {}

    # Report first (titles), data-dir overrides with fresher prose
    if args.report and args.report.is_file():
        p, t = collect_from_report(args.report)
        prose.update(p)
        titles.update(t)
    if args.data_dir and args.data_dir.is_dir():
        p, t = collect_from_data_dir(args.data_dir)
        prose.update(p)
        for k, v in t.items():
            titles.setdefault(k, v)

    if not prose:
        print("Error: no chapter prose found")
        raise SystemExit(1)

    lines = [f"# {args.title}", ""]
    chapter_nums = sorted(prose)
    lines.append(f"> 章节数：{len(chapter_nums)}（第{chapter_nums[0]}章 — 第{chapter_nums[-1]}章）")
    total_chars = sum(len(p) for p in prose.values())
    lines.append(f"> 总字数：约 {total_chars} 字")
    lines.extend(["", "---", ""])

    for num in chapter_nums:
        title = titles.get(num, "")
        heading = f"## 第{num}章" + (f" {title}" if title else "")
        lines.extend([heading, "", prose[num], "", "---", ""])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Assembled {len(chapter_nums)} chapters, {total_chars} total chars")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
