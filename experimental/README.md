# experimental/ — designed-but-unintegrated subsystems

Everything under this directory is a **next-generation rewrite that is NOT wired
into the running system**. The live pipeline (`core_generator.py` → `NovelGenerator`)
imports **none** of it. These modules were previously scattered at the project root
and described in `PROGRESS_SUMMARY.md` as "100% complete", which was misleading:
they are complete as standalone code but were never integrated. They are quarantined
here so the working system's import surface stays small and the project's real status
is honest.

## Contents

| Path | What it is | Status |
|------|------------|--------|
| `memory_system/` | Cognitive four-layer memory (working / episodic / semantic / procedural / unified) | unintegrated |
| `plot_engine/` | Foreshadowing lifecycle + multi-thread story-arc controller | unintegrated |
| `evaluation/` | Iterative refinement loop + token-aware context-integrity assembly | unintegrated |
| `core/` | Event bus + plugin manager + multi-LLM scheduler | unintegrated |

## Active counterparts (what the runtime actually uses)

- Memory: `memory_system/{sliding_window,entity_state,hierarchical_summary,long_term_memory,character_relationship}.py`
- Continuity scoring: `evaluation/continuity_v2.py`

## Importing

These packages reference stable top-level modules (`config`, `llm_client`,
`embedding_service`, `utils.token_counter`) and each other via relative imports,
so run from the project root:

```python
from experimental.memory_system import UnifiedMemorySystem
from experimental.plot_engine import ForeshadowingEngine, StoryArcController
from experimental.evaluation import IterativeRefinement, ContextIntegrityManager
from experimental.core import EventBus, PluginManager, LLMScheduler
```

## To integrate one of these

1. Wire it into `NovelGenerator.__init__` / the generation workflow.
2. Add a migration path for any persisted legacy data.
3. Add tests (`tests/`) and update `PROGRESS_SUMMARY.md`'s integration checklist.

Until those steps are done for a module, treat it as scaffolding, not behavior.
