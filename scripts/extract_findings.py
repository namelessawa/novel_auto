"""Extract findings + verdicts from workflow agent jsonl transcripts."""
import json
import sys
from pathlib import Path

DIR = Path(r"C:/Users/Lenovo/.claude/projects/E--pythonproject-novel-auto/edeb3e8e-535e-477d-9158-a9b85cd66824/subagents/workflows/wf_944c4346-92d")

findings = []  # finder outputs (list of {findings: [...]})
verdicts = []  # verifier outputs (single object)

for f in sorted(DIR.glob("agent-*.jsonl")):
    last_structured = None
    last_label = None
    try:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message", {})
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use" and block.get("name") == "StructuredOutput":
                        last_structured = block.get("input", {})
    except OSError:
        continue
    # also peek at meta.json
    meta_file = f.with_suffix(".meta.json")
    label = None
    if meta_file.exists():
        try:
            with open(meta_file, encoding="utf-8") as mh:
                meta = json.load(mh)
            label = meta.get("label")
        except (OSError, json.JSONDecodeError):
            pass

    if last_structured is None:
        continue
    # heuristics: finder has "findings" array, verifier has "is_real_bug"
    if "findings" in last_structured:
        findings.append({"file": f.name, "label": label, "data": last_structured})
    elif "is_real_bug" in last_structured:
        verdicts.append({"file": f.name, "label": label, "data": last_structured})

print(f"Found {len(findings)} finder outputs, {len(verdicts)} verdicts", file=sys.stderr)

# We have findings.findings[] and verdicts. The verifier prompt embeds the finding's id,
# title, file, etc. Match by reading the verifier's prompt content.
# But the JSON output of verifier doesn't include the finding id directly.
# We need to find the original prompt (user message) of each verifier to extract finding id.

def first_user_prompt(jsonl_path):
    try:
        with open(jsonl_path, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if rec.get("type") == "user":
                    msg = rec.get("message", {})
                    content = msg.get("content")
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                return b.get("text", "")
                            if isinstance(b, dict) and "text" in b:
                                return b.get("text", "")
                    if isinstance(content, str):
                        return content
                    break
    except (OSError, json.JSONDecodeError):
        pass
    return ""

# Enrich verdicts with finding id parsed from prompt
import re
for v in verdicts:
    prompt = first_user_prompt(DIR / v["file"])
    m_title = re.search(r"- title:\s*([^\n]+)", prompt)
    m_file = re.search(r"- file:\s*([^\n]+)", prompt)
    m_problem = re.search(r"- problem:\s*([^\n]+)", prompt)
    v["finding_title"] = (m_title.group(1).strip() if m_title else "")
    v["finding_file"] = (m_file.group(1).strip() if m_file else "")
    v["finding_problem"] = (m_problem.group(1).strip() if m_problem else "")

# Build a flat list of finding rows with their verdict (matched by title)
all_findings_flat = []
for finder in findings:
    label = finder["label"]
    for f in finder["data"].get("findings", []):
        all_findings_flat.append({
            "finder_label": label,
            "finder_file": finder["file"],
            "id": f.get("id"),
            "severity": f.get("severity"),
            "dimension": f.get("dimension"),
            "title": f.get("title"),
            "file": f.get("file"),
            "line_hint": f.get("line_hint", ""),
            "problem": f.get("problem"),
            "impact": f.get("impact"),
            "fix_sketch": f.get("fix_sketch"),
            "confidence": f.get("confidence"),
        })

# Match verdict by title
title_to_verdict = {}
for v in verdicts:
    t = v["finding_title"]
    if t:
        title_to_verdict[t] = v["data"]

for row in all_findings_flat:
    v = title_to_verdict.get(row["title"])
    if v:
        row["is_real_bug"] = v.get("is_real_bug")
        row["verdict_reasoning"] = v.get("reasoning")
        row["refined_fix"] = v.get("refined_fix")
        row["verdict_confidence"] = v.get("confidence")
    else:
        row["is_real_bug"] = None

out = {
    "total_findings": len(all_findings_flat),
    "real_bugs": [r for r in all_findings_flat if r.get("is_real_bug") is True],
    "false_positives": [r for r in all_findings_flat if r.get("is_real_bug") is False],
    "unverified": [r for r in all_findings_flat if r.get("is_real_bug") is None],
}
sys.stdout.reconfigure(encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
