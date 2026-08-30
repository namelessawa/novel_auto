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
import os
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
# Main Runner
# ---------------------------------------------------------------------------


async def run_pipeline_e2e(
    provider_file: Path,
    chapters: int = 3,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the full pipeline and generate a report."""

    # Import after path setup
    from nf_core import provider_runtime
    from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
    from story.stateful_pipeline.models import (
        ChapterGenerationPreference,
        ForeshadowMode,
    )
    from story.stateful_pipeline.service import StatefulPipelineService
    from story.models import StoryBible, CanonicalState
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

    # Create temporary novel directory
    novel_id = f"e2e_test_{uuid.uuid4().hex[:8]}"
    data_dir = output_dir / "novel_data"
    data_dir.mkdir(parents=True, exist_ok=True)

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
        # Create StoryBible
        print("[E2E] Creating StoryBible...")
        bible = StoryBible(
            title="测试小说",
            genre="玄幻",
            premise="一个少年获得神秘力量，踏上修仙之路",
            main_conflicts=["正邪两道的对抗"],
            theme="成长与选择",
            style_contract={"narrative_voice": "第三人称", "pacing": "medium"},
        )
        bible_store = StoryBibleStore(str(data_dir))
        bible_store.save(bible)

        # Load existing CanonicalState (store creates default with revision 1)
        canon_store = CanonicalStateStore(str(data_dir))
        canon = canon_store.load()
        print(f"[E2E] CanonicalState revision: {canon.revision}")

        # Create pipeline service
        chroma_dir = output_dir / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        chroma_repo = ChromaMemoryRepository(persist_dir=str(chroma_dir))

        service = StatefulPipelineService(
            data_dir=str(data_dir),
            chroma_repo=chroma_repo,
        )

        # Generate synopses
        print("[E2E] Generating synopses for chapters 1-2...")
        synopses = await service.generate_initial_synopses(
            novel_id=novel_id,
            story_bible=bible,
            genre="玄幻",
        )
        print(f"[E2E] Generated {len(synopses)} synopses")

        # Ensure schema
        print("[E2E] Ensuring information schema...")
        schema = await service.ensure_schema(
            novel_id=novel_id,
            story_bible=bible,
            genre="玄幻",
            synopses=synopses,
        )
        print(f"[E2E] Schema has {len(schema.fields)} fields: {schema.field_keys}")

        # Run chapters
        for chapter in range(1, chapters + 1):
            print(f"\n[E2E] === Chapter {chapter} ===")

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
    args = parser.parse_args()

    if not args.provider_file.exists():
        print(f"Error: Provider file not found: {args.provider_file}")
        sys.exit(1)

    asyncio.run(run_pipeline_e2e(
        provider_file=args.provider_file,
        chapters=args.chapters,
        output_dir=args.output_dir,
    ))


if __name__ == "__main__":
    main()
