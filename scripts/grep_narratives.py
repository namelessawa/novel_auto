"""Phase 6 iter#QQQ — CLI grep across narratives/*.txt.

/api/tick/narratives/search 的 CLI 对偶. Reader 没起时 (开发/调试/bench 后)
直接搜.

Usage:
    python scripts/grep_narratives.py <novel_dir> "关键词"
    python scripts/grep_narratives.py backend/data/users/bench/novels/bench_phase6a-500tick-republic-iterN_* "苏默"
    python scripts/grep_narratives.py --start-tick 100 --end-tick 200 <dir> "档案馆"

Output: 每命中一行 'tick N: ...snippet...'

支持 glob (shell 展开). 多 novel_dir 顺序搜.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _search_dir(
    novel_dir: Path, q: str, start_tick: int, end_tick: int, limit: int
) -> list[tuple[int, str]]:
    """Return [(tick, snippet)] matches."""
    narratives_dir = novel_dir / "narratives"
    if not narratives_dir.is_dir():
        return []
    pat = re.compile(r"^tick_(\d{6})\.txt$")
    out: list[tuple[int, str]] = []
    for fname in sorted(os.listdir(narratives_dir)):
        m = pat.match(fname)
        if not m:
            continue
        tick = int(m.group(1))
        if start_tick > 0 and tick < start_tick:
            continue
        if end_tick > 0 and tick > end_tick:
            continue
        path = narratives_dir / fname
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        idx = text.find(q)
        if idx < 0:
            continue
        snippet_start = max(0, idx - 40)
        snippet_end = min(len(text), idx + len(q) + 40)
        snippet = text[snippet_start:snippet_end].replace("\n", " ")
        if snippet_start > 0:
            snippet = "…" + snippet
        if snippet_end < len(text):
            snippet = snippet + "…"
        out.append((tick, snippet))
        if len(out) >= limit:
            break
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="grep across narratives/*.txt")
    p.add_argument("novel_dir", nargs="+", help="novel data dir (含 narratives/ 子目录)")
    p.add_argument("q", help="搜索关键词 (literal)")
    p.add_argument("--start-tick", type=int, default=0)
    p.add_argument("--end-tick", type=int, default=0, help="0 = 不限")
    p.add_argument("--limit", type=int, default=100)
    args = p.parse_args()

    if not args.q:
        print("ERR: q (关键词) 不可为空", file=sys.stderr)
        return 2

    total = 0
    for d in args.novel_dir:
        path = Path(d)
        if not path.is_dir():
            print(f"WARN: skip {d!r} (不是目录)", file=sys.stderr)
            continue
        matches = _search_dir(path, args.q, args.start_tick, args.end_tick, args.limit)
        if not matches:
            continue
        if len(args.novel_dir) > 1:
            print(f"=== {path.name} ({len(matches)} matches) ===")
        for tick, snippet in matches:
            print(f"tick {tick}: {snippet}")
            total += 1
    if total == 0:
        print(f"no matches for {args.q!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
