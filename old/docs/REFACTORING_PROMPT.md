# Novel Auto-Generation System Refactoring Prompt

You are tasked with refactoring the `novel_auto` project to resolve critical architectural issues and implement key innovations. Follow this strict workflow:

## Phase 1: Foundation Fixes (Must Complete Before Any Other Work)

### 1.1 Implement Missing Embedding Service
- Create `embedding_service.py` with `EmbeddingService` class
- Use `sentence-transformers` library with configurable model (default: `BAAI/bge-small-zh-v1.5`)
- Implement methods: `embed_texts(texts: List[str]) -> List[List[float]]`, `embed_query(query: str) -> List[float]`
- Add graceful fallback to keyword matching when model unavailable
- **Write unit tests** covering: embedding generation, batch processing, error handling, fallback behavior

### 1.2 Standardize Token-Based Memory Management
- Refactor `SlidingWindowMemory` to use `tiktoken` for accurate token counting (not character count)
- Update all memory modules to use consistent token-based limits
- Create shared `TokenCounter` utility class
- **Write unit tests** covering: token counting accuracy, eviction at boundaries, edge cases (mixed languages)

### 1.3 Integrate Advanced Continuity Evaluator
- Replace `ChapterContinuityEvaluator` usage in `core_generator.py` with `EnhancedContinuityEvaluator` from `evaluation/continuity_v2.py`
- Wire up all 8 evaluation dimensions (CHARACTER, PLOT, SETTING, THEME, STYLE, TEMPORAL, RELATIONSHIP, FORESHADOWING)
- Implement evaluation result persistence to `evaluation_results.json`
- **Write unit tests** covering: each dimension scoring, issue detection, heuristic fallback, caching behavior

## Phase 2: Memory System Unification

### 2.1 Deprecate Legacy Memory System
- Create migration path from legacy modules to unified cognitive system
- Implement `MemoryMigration` utility to convert legacy data to new format
- **Write unit tests** covering: data migration integrity, backward compatibility

### 2.2 Activate UnifiedMemorySystem
- Wire `UnifiedMemorySystem` into `NovelGenerator.__init__()`
- Implement cross-layer memory queries for optimized prompt building
- **Write unit tests** covering: each memory layer independently, cross-layer queries, consolidation logic

### 2.3 Implement Memory Eviction Policy
- Create `MemoryEvictionPolicy` class with importance scoring algorithm
- Implement "forgetting curve" - compress low-importance events to summaries
- Add configuration for max events and compression threshold
- **Write unit tests** covering: importance scoring, eviction triggers, summary compression

## Phase 3: Quality Assurance Infrastructure

### 3.1 Create Comprehensive Test Suite
- Create `tests/` directory with proper structure:
  ```
  tests/
  ├── unit/
  │   ├── memory/
  │   │   ├── test_sliding_window.py
  │   │   ├── test_entity_state.py
  │   │   ├── test_hierarchical_summary.py
  │   │   ├── test_long_term_memory.py
  │   │   └── test_unified_memory.py
  │   ├── test_embedding_service.py
  │   ├── test_core_generator.py
  │   ├── test_continuity_evaluator.py
  │   └── test_token_counter.py
  ├── integration/
  │   ├── test_memory_integration.py
  │   └── test_generation_pipeline.py
  └── conftest.py
  ```
- Use `pytest` with `pytest-asyncio` for async tests
- Mock external API calls (DeepSeek) using `pytest-mock`
- Achieve minimum **80% test coverage**

### 3.2 Implement Test Fixtures
- Create sample novel data in `tests/fixtures/`
- Mock LLM responses for deterministic testing
- Create test utilities for memory state setup/teardown

## Testing Requirements (MANDATORY)

For EVERY module you modify or create:

1. **Write tests FIRST** (TDD approach):
   - Write failing test describing expected behavior
   - Implement minimum code to pass
   - Refactor while keeping tests green

2. **Test coverage requirements**:
   - All new functions: 100% coverage
   - Modified functions: 100% coverage of new logic
   - Overall project: minimum 80%

3. **Test types required**:
   - Unit tests for all public methods
   - Edge case tests (empty input, null values, boundary conditions)
   - Error handling tests (API failures, invalid data)
   - Integration tests for module interactions

4. **Run tests after each change**:
   ```bash
   pytest tests/ -v --cov=. --cov-report=term-missing
   ```

## Validation Checklist

Before marking any task complete:

- [ ] All unit tests pass
- [ ] Test coverage ≥ 80% for modified modules
- [ ] No hardcoded values (use config)
- [ ] Type hints added to all new functions
- [ ] Docstrings added to all public methods
- [ ] Error handling implemented
- [ ] No silent failures (all errors logged or raised)

## File Output

After completing all phases, output:

1. **Refactoring Summary Report** (`REFACTORING_REPORT.md`):
   - Changes made to each file
   - Test coverage achieved
   - Known limitations

2. **Migration Guide** (`MIGRATION_GUIDE.md`):
   - How to upgrade existing novels to new memory system
   - Breaking changes and deprecations

## Execution Order

```
Phase 1.1 → Phase 1.2 → Phase 1.3
    ↓
Phase 2.1 → Phase 2.2 → Phase 2.3
    ↓
Phase 3.1 + Phase 3.2 (parallel)
    ↓
Validation Checklist
    ↓
Output Reports
```

**DO NOT proceed to next phase until all tests in current phase pass.**

Begin with Phase 1.1: Create `embedding_service.py` with full unit tests.
