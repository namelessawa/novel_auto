"""End-to-end pipeline runner with full LLM and ChromaDB reporting.

Runs the stateful generation pipeline for 3 chapters using coding.txt
provider credentials, capturing all LLM inputs/outputs and vector DB state.

Usage:
    python scripts/run_pipeline_e2e.py --provider-file coding.txt --chapters 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Add backend to path
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
_PROJECT_ROOT = _BACKEND_DIR.parent
for p in (str(_PROJECT_ROOT), str(_BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# LLM Call Recorder
# ---------------------------------------------------------------------------


class LLMCallRecorder:
    """Records all LLM calls with inputs and outputs."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self._original_chat = None

    def install(self):
        """Monkey-patch llm_client.chat to record calls."""
        from nf_core import llm_client as llm_module

        self._original_chat = llm_module.llm_client.chat
        recorder = self

        async def recording_chat(*args, **kwargs):
            call_record = {
                "timestamp": datetime.now().isoformat(),
                "agent_id": kwargs.get("agent_id", "unknown"),
                "system_prompt": kwargs.get("system_prompt", "")[:500],  # truncate
                "user_prompt": kwargs.get("user_prompt", "")[:2000],  # truncate
                "temperature": kwargs.get("temperature"),
                "max_tokens": kwargs.get("max_tokens"),
            }
            try:
                response = await recorder._original_chat(*args, **kwargs)
                call_record["output"] = response.content[:3000]  # truncate
                call_record["success"] = True
                call_record["usage"] = {
                    "prompt_tokens": getattr(response, "prompt_tokens", 0),
                    "completion_tokens": getattr(response, "completion_tokens", 0),
                }
            except Exception as exc:
                call_record["output"] = str(exc)
                call_record["success"] = False
                raise
            finally:
                recorder.calls.append(call_record)
            return response

        llm_module.llm_client.chat = recording_chat

    def uninstall(self):
        """Restore original llm_client.chat."""
        if self._original_chat:
            from nf_core import llm_client as llm_module
            llm_module.llm_client.chat = self._original_chat

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all calls."""
        by_agent: dict[str, list] = {}
        for call in self.calls:
            agent = call["agent_id"]
            if agent not in by_agent:
                by_agent[agent] = []
            by_agent[agent].append(call)

        return {
            "total_calls": len(self.calls),
            "successful_calls": sum(1 for c in self.calls if c["success"]),
            "failed_calls": sum(1 for c in self.calls if not c["success"]),
            "calls_by_agent": {
                agent: len(calls) for agent, calls in by_agent.items()
            },
            "total_prompt_tokens": sum(
                c.get("usage", {}).get("prompt_tokens", 0) for c in self.calls
            ),
            "total_completion_tokens": sum(
                c.get("usage", {}).get("completion_tokens", 0) for c in self.calls
            ),
        }


# ---------------------------------------------------------------------------
# Chapter prose persistence
# ---------------------------------------------------------------------------


def _extract_prose(content: str) -> str:
    """Extract prose from <prose> tags, falling back to raw content."""
    if "<prose>" in content and "</prose>" in content:
        start = content.find("<prose>") + len("<prose>")
        end = content.find("</prose>")
        return content[start:end].strip()
    return content.strip()


def _prose_path(data_dir: Path, chapter: int) -> Path:
    return Path(data_dir) / "pipeline" / f"prose_ch{chapter}.md"


def _save_chapter_prose(recorder: "LLMCallRecorder", data_dir: Path, chapter: int) -> None:
    """Persist the last writer output for this chapter as prose_ch{N}.md."""
    writer_calls = [
        c for c in recorder.calls
        if c.get("agent_id") == "pipeline_simplified_writer" and c.get("success")
    ]
    if not writer_calls:
        return
    prose = _extract_prose(writer_calls[-1]["output"])
    if prose:
        path = _prose_path(data_dir, chapter)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prose, encoding="utf-8")
        print(f"[E2E] Saved chapter {chapter} prose ({len(prose)} chars) to {path.name}")


def _backfill_prose_from_report(report_path: Path, data_dir: Path) -> None:
    """Backfill prose_ch{N}.md for chapters missing them, from an old report.

    Writer calls appear in chapter order in the report's llm_calls list.
    """
    if not report_path.is_file():
        return
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    writer_calls = [
        c for c in report.get("llm_calls", [])
        if c.get("agent_id") == "pipeline_simplified_writer" and c.get("success")
    ]
    # Map by chapter from pipeline_states order when possible
    states = [
        s for s in report.get("pipeline_states", [])
        if s.get("phase") == "chapter_completed"
    ]
    completed = [s["chapter"] for s in states]
    for idx, call in enumerate(writer_calls):
        chapter = completed[idx] if idx < len(completed) else idx + 1
        path = _prose_path(data_dir, chapter)
        if path.exists():
            continue
        prose = _extract_prose(call.get("output", ""))
        if prose:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(prose, encoding="utf-8")
            print(f"[E2E] Backfilled chapter {chapter} prose from old report")


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------


async def run_pipeline_e2e(
    provider_file: Path,
    chapters: int = 3,
    output_dir: Path | None = None,
    resume_novel_id: str | None = None,
) -> dict[str, Any]:
    """Run the full pipeline and generate a report.

    When resume_novel_id is given together with an existing output_dir,
    the run continues that novel: bible/canon/synopsis/schema are loaded
    from the stores and already-completed chapters are skipped.
    """
    resume = resume_novel_id is not None

    # Import after path setup
    from nf_core import provider_runtime
    from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
    from story.stateful_pipeline.models import (
        ChapterGenerationPreference,
        ForeshadowMode,
    )
    from story.stateful_pipeline.service import StatefulPipelineService
    from story.models import StoryBible
    from story.persistence import StoryBibleStore, CanonicalStateStore

    # Setup output directory
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="pipeline_e2e_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[E2E] Output directory: {output_dir}")
    print(f"[E2E] Provider file: {provider_file}")
    print(f"[E2E] Chapters to generate: {chapters}")

    # Load provider config
    print("[E2E] Loading provider configuration...")
    provider_config = provider_runtime.ProviderRuntimeConfig.from_provider_file(provider_file)
    print(f"[E2E] Provider: {provider_config.provider}, Model: {provider_config.model}")

    # Override thinking_mode since glm-5.3 doesn't support thinking parameter
    import dataclasses
    provider_config = dataclasses.replace(provider_config, thinking_mode="")

    # Set up provider runtime
    provider_runtime.set_request_provider_config(provider_config)

    # Create temporary novel directory (or reuse for resume)
    novel_id = resume_novel_id or f"e2e_test_{uuid.uuid4().hex[:8]}"
    data_dir = output_dir / "novel_data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if resume:
        # Backfill prose_ch{N}.md for chapters completed in the previous run.
        old_report = output_dir / "pipeline_e2e_report.json"
        _backfill_prose_from_report(old_report, data_dir)
        # Archive the previous report so this run's report doesn't overwrite it.
        if old_report.is_file():
            old_report.replace(output_dir / "pipeline_e2e_report_prev.json")

    print(f"[E2E] Novel ID: {novel_id}")
    print(f"[E2E] Data directory: {data_dir}")

    # Initialize recorder
    recorder = LLMCallRecorder()
    recorder.install()

    report = {
        "run_id": novel_id,
        "started_at": datetime.now().isoformat(),
        "provider": {
            "provider": provider_config.provider,
            "model": provider_config.model,
            "base_url": provider_config.base_url,
        },
        "chapters_requested": chapters,
        "chapters_completed": 0,
        "llm_calls": [],
        "chroma_state": {},
        "pipeline_states": [],
        "errors": [],
    }

    try:
        bible_store = StoryBibleStore(str(data_dir))
        canon_store = CanonicalStateStore(str(data_dir))

        if resume:
            # Continue an existing novel: load persisted authorities.
            print("[E2E] Resume mode: loading StoryBible and CanonicalState...")
            bible = bible_store.load()
            canon = canon_store.load()
            print(f"[E2E] Loaded bible '{bible.title}' R{bible.revision}, canon R{canon.revision}")
        else:
            # Create StoryBible with complete data for NarrativeContractBuilder
            print("[E2E] Creating StoryBible...")
            bible = StoryBible(
                title="测试小说",
                genre="都市生活",
                premise="一个普通上班族在大都市中追求梦想，经历职场起伏与情感波折",
                main_conflicts=["职场竞争与个人理想的冲突"],
                theme="成长与选择",
                setting_summary="繁华都市，现代写字楼与老街巷弄交织",
                protagonist_contracts=["李明是主角，30岁，互联网公司项目经理"],
                immutable_world_rules=["现实都市背景，无超自然元素", "职场规则真实可信"],
                style_contract={"narrative_voice": "第三人称", "pacing": "medium"},
            )
            bible_store.save(bible)

            # Load existing CanonicalState and add characters
            canon = canon_store.load()
            # Add protagonist character for NarrativeContractBuilder validation
            canon.characters["li_ming"] = {
                "name": "李明",
                "role": "protagonist",
                "status": "active",
            }
            # Increment revision before saving
            updated_canon = canon.model_copy(update={"revision": canon.revision + 1})
            canon_store.save_next(updated_canon, expected_revision=canon.revision)
            canon = updated_canon
            print(f"[E2E] CanonicalState revision: {canon.revision}")

        # Create pipeline service
        chroma_dir = output_dir / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        chroma_repo = ChromaMemoryRepository(persist_dir=str(chroma_dir))

        service = StatefulPipelineService(
            data_dir=str(data_dir),
            chroma_repo=chroma_repo,
        )

        # Generate synopses (or load existing on resume)
        if resume:
            from story.stateful_pipeline.persistence import SynopsisStore
            synopses = SynopsisStore(str(data_dir)).load_all(novel_id)
            print(f"[E2E] Resume mode: loaded {len(synopses)} existing synopses")
        else:
            print("[E2E] Generating synopses for chapters 1-2...")
            synopses = await service.generate_initial_synopses(
                novel_id=novel_id,
                story_bible=bible,
                genre="都市生活",
            )
            print(f"[E2E] Generated {len(synopses)} synopses")

        # Ensure schema
        print("[E2E] Ensuring information schema...")
        schema = await service.ensure_schema(
            novel_id=novel_id,
            story_bible=bible,
            genre="都市生活",
            synopses=synopses,
        )
        print(f"[E2E] Schema has {len(schema.fields)} fields: {schema.field_keys}")

        # Run chapters
        from story.stateful_pipeline.models import ChapterPipelinePhase

        for chapter in range(1, chapters + 1):
            print(f"\n[E2E] === Chapter {chapter} ===")

            # Resume: skip chapters already completed in a previous run
            prev_state = service.get_pipeline_state(novel_id, chapter)
            if prev_state is not None and prev_state.phase == ChapterPipelinePhase.COMPLETED:
                print(f"[E2E] Chapter {chapter} already completed — skipping")
                report["chapters_completed"] += 1
                report["pipeline_states"].append({
                    "chapter": chapter,
                    "phase": "chapter_completed",
                    "resumed_skip": True,
                })
                chroma_count = await chroma_repo.count(novel_id)
                report["chroma_state"][f"after_chapter_{chapter}"] = {
                    "document_count": chroma_count,
                }
                continue

            # Create preference
            preference = ChapterGenerationPreference(
                novel_id=novel_id,
                chapter_number=chapter,
                foreshadow_mode=ForeshadowMode.RANDOM,
            )

            # Confirm chapter
            print(f"[E2E] Confirming chapter {chapter}...")
            confirmation = service.confirm_chapter(
                novel_id=novel_id,
                chapter=chapter,
                preference=preference,
                bible=bible,
                canon=canon,
                style_revision=1,
            )

            # Run pipeline
            print(f"[E2E] Running pipeline for chapter {chapter}...")
            try:
                state = await service.run_chapter_pipeline(
                    novel_id=novel_id,
                    chapter=chapter,
                    confirmation=confirmation,
                    bible=bible,
                    canon=canon,
                    style_prefix="",
                    chapter_goal=f"推进第{chapter}章剧情",
                )
                report["chapters_completed"] += 1
                report["pipeline_states"].append({
                    "chapter": chapter,
                    "phase": state.phase.value,
                    "synopsis_revision": state.synopsis_revision,
                })
                print(f"[E2E] Chapter {chapter} completed: {state.phase.value}")

                # Persist the chapter prose (from the last writer call)
                _save_chapter_prose(recorder, data_dir, chapter)
            except Exception as exc:
                error_msg = f"Chapter {chapter} failed: {exc}"
                print(f"[E2E] ERROR: {error_msg}")
                report["errors"].append(error_msg)
                report["pipeline_states"].append({
                    "chapter": chapter,
                    "phase": "failed",
                    "error": str(exc),
                })

            # Record ChromaDB state after each chapter
            chroma_count = await chroma_repo.count(novel_id)
            report["chroma_state"][f"after_chapter_{chapter}"] = {
                "document_count": chroma_count,
            }
            print(f"[E2E] ChromaDB documents after chapter {chapter}: {chroma_count}")

        # Final ChromaDB query
        print("\n[E2E] Querying ChromaDB for final state...")
        final_query = await chroma_repo.query(novel_id, "主角", top_k=5)
        report["chroma_state"]["final_query_sample"] = [
            {"content": d["content"][:100], "metadata": d["metadata"]}
            for d in final_query[:3]
        ]

    except Exception as exc:
        error_msg = f"Pipeline run failed: {exc}"
        print(f"[E2E] FATAL ERROR: {error_msg}")
        report["errors"].append(error_msg)
        import traceback
        traceback.print_exc()

    finally:
        recorder.uninstall()

    # Collect LLM calls
    report["llm_calls"] = recorder.calls
    report["llm_summary"] = recorder.get_summary()
    report["completed_at"] = datetime.now().isoformat()

    # Save report
    report_path = output_dir / "pipeline_e2e_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[E2E] Report saved to: {report_path}")

    # Generate markdown summary
    md_path = output_dir / "pipeline_e2e_summary.md"
    _write_markdown_report(report, md_path)
    print(f"[E2E] Markdown summary saved to: {md_path}")

    return report


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    """Write a markdown summary of the E2E run."""
    lines = [
        "# Pipeline E2E Run Report",
        "",
        f"**Run ID**: {report['run_id']}",
        f"**Started**: {report['started_at']}",
        f"**Completed**: {report['completed_at']}",
        "",
        "## Provider Configuration",
        "",
        f"- Provider: {report['provider']['provider']}",
        f"- Model: {report['provider']['model']}",
        f"- Base URL: {report['provider']['base_url']}",
        "",
        "## Summary",
        "",
        f"- Chapters requested: {report['chapters_requested']}",
        f"- Chapters completed: {report['chapters_completed']}",
        f"- Total LLM calls: {report['llm_summary']['total_calls']}",
        f"- Successful calls: {report['llm_summary']['successful_calls']}",
        f"- Failed calls: {report['llm_summary']['failed_calls']}",
        f"- Total prompt tokens: {report['llm_summary']['total_prompt_tokens']}",
        f"- Total completion tokens: {report['llm_summary']['total_completion_tokens']}",
        "",
        "## LLM Calls by Agent",
        "",
    ]

    for agent, count in report["llm_summary"]["calls_by_agent"].items():
        lines.append(f"- {agent}: {count} calls")

    lines.extend([
        "",
        "## Pipeline States",
        "",
    ])

    for state in report["pipeline_states"]:
        lines.append(f"- Chapter {state['chapter']}: {state['phase']}")

    lines.extend([
        "",
        "## ChromaDB State",
        "",
    ])

    for key, value in report["chroma_state"].items():
        if isinstance(value, dict) and "document_count" in value:
            lines.append(f"- {key}: {value['document_count']} documents")

    if report["errors"]:
        lines.extend([
            "",
            "## Errors",
            "",
        ])
        for error in report["errors"]:
            lines.append(f"- {error}")

    lines.extend([
        "",
        "## LLM Call Details",
        "",
    ])

    for i, call in enumerate(report["llm_calls"][:20], 1):  # Limit to first 20
        lines.extend([
            f"### Call {i}: {call['agent_id']}",
            "",
            f"- Timestamp: {call['timestamp']}",
            f"- Success: {call['success']}",
            f"- Temperature: {call.get('temperature')}",
            f"- Max tokens: {call.get('max_tokens')}",
            "",
            "**System Prompt (truncated)**:",
            "```",
            call["system_prompt"][:200] + "..." if len(call["system_prompt"]) > 200 else call["system_prompt"],
            "```",
            "",
            "**User Prompt (truncated)**:",
            "```",
            call["user_prompt"][:300] + "..." if len(call["user_prompt"]) > 300 else call["user_prompt"],
            "```",
            "",
            "**Output (truncated)**:",
            "```",
            call["output"][:300] + "..." if len(call["output"]) > 300 else call["output"],
            "```",
            "",
        ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Run pipeline E2E test")
    parser.add_argument(
        "--provider-file",
        type=Path,
        default=Path("coding.txt"),
        help="Path to provider credentials file",
    )
    parser.add_argument(
        "--chapters",
        type=int,
        default=3,
        help="Number of chapters to generate",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for report",
    )
    parser.add_argument(
        "--resume-dir",
        type=Path,
        default=None,
        help="Resume an existing run: reuse this output directory (skips completed chapters)",
    )
    parser.add_argument(
        "--novel-id",
        type=str,
        default=None,
        help="Novel id to resume (required with --resume-dir)",
    )
    args = parser.parse_args()

    if not args.provider_file.exists():
        print(f"Error: Provider file not found: {args.provider_file}")
        sys.exit(1)

    output_dir = args.output_dir
    resume_novel_id = None
    if args.resume_dir is not None:
        if not args.resume_dir.is_dir():
            print(f"Error: resume dir not found: {args.resume_dir}")
            sys.exit(1)
        if not args.novel_id:
            print("Error: --novel-id is required with --resume-dir")
            sys.exit(1)
        output_dir = args.resume_dir
        resume_novel_id = args.novel_id

    asyncio.run(run_pipeline_e2e(
        provider_file=args.provider_file,
        chapters=args.chapters,
        output_dir=output_dir,
        resume_novel_id=resume_novel_id,
    ))


if __name__ == "__main__":
    main()
