"""Single-call author writer and one-shot targeted repair adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client
from nf_core.provider_runtime import (
    ProviderError,
    ProviderRuntimeReceipt,
    provider_output_invalid,
    resolve_provider_runtime,
)
from story.chapter_plan import ChapterPlan
from story.context_builder import ContextPackage
from story.models import SectionGoal, WriterCandidate
from story.repair_patch import (
    ProviderRepairPatchSet,
    RepairPatchSet,
)
from story.repair_plan import RepairPlan, repair_patch_prompt_payload


_WRITER_BLOCK_GROUPS = (
    ("opening", ("opening_1", "opening_2")),
    (
        "development",
        ("development_1", "development_2", "development_3"),
    ),
    ("conflict", ("conflict_1", "conflict_2", "conflict_3")),
    ("resolution", ("resolution_1", "resolution_2")),
)
_WRITER_BLOCK_NAMES = tuple(
    block_name
    for _group_name, block_names in _WRITER_BLOCK_GROUPS
    for block_name in block_names
)
_WRITER_CELL_COUNT_BY_GROUP = {
    "opening": 4,
    "development": 6,
    "conflict": 6,
    "resolution": 4,
}
_WRITER_GROUP_PREFIX = {
    "opening": "o",
    "development": "d",
    "conflict": "c",
    "resolution": "r",
}
_WRITER_BLOCK_CELL_NAMES = {
    block_name: tuple(
        f"{_WRITER_GROUP_PREFIX[group_name]}{block_index}u{cell_index}"
        for cell_index in range(1, _WRITER_CELL_COUNT_BY_GROUP[group_name] + 1)
    )
    for group_name, block_names in _WRITER_BLOCK_GROUPS
    for block_index, block_name in enumerate(block_names, start=1)
}
_WRITER_CELL_NAMES = tuple(
    cell_name
    for block_name in _WRITER_BLOCK_NAMES
    for cell_name in _WRITER_BLOCK_CELL_NAMES[block_name]
)
_WRITER_TOTAL_PROSE_LEAF_COUNT = len(_WRITER_CELL_NAMES)
_WRITER_PROVIDER_DRAFTING_HEADROOM = 10
_WRITER_SENTENCE_BOUNDARIES = frozenset("。！？!?；;")
_REPAIR_CELL_NAMES = ("beat_1", "beat_2", "beat_3")


class WriterOutputError(RuntimeError):
    pass


@dataclass(frozen=True)
class WriterResult:
    candidate: WriterCandidate
    usage: dict[str, int]
    structured_output_repair_count: int = 0
    primary_output_contract_pass: bool = True
    provider: str = ""
    provider_model: str = ""
    provider_source: str = ""
    provider_config_fingerprint: str = ""
    ignored_fields: list[str] = field(default_factory=list)
    audit_codes: list[str] = field(default_factory=list)
    writer_block_nonspace_lengths: list[int] = field(default_factory=list)
    writer_cell_nonspace_lengths: list[int] = field(default_factory=list)
    writer_cell_sentence_boundary_counts: list[int] = field(default_factory=list)
    repair_patches: RepairPatchSet | None = None
    provider_repair_patches: ProviderRepairPatchSet | None = None


@dataclass(frozen=True)
class PlannerResult:
    plan: ChapterPlan
    usage: dict[str, int]


class WriterProtocol(Protocol):
    async def plan(self, context: ContextPackage, goal: SectionGoal) -> PlannerResult: ...

    async def generate(self, context: ContextPackage, goal: SectionGoal) -> WriterResult: ...

    async def repair(
        self, candidate: WriterCandidate, plan: RepairPlan
    ) -> WriterResult: ...


class AuthorWriter:
    def __init__(self, style_prompt_prefix: str = "") -> None:
        """Initialize writer with optional per-style prompt prefix.

        The prefix is prepended to the Novel Writer system prompt only.
        It does not affect planner, repair, or other LLM roles.
        """
        self._style_prompt_prefix = style_prompt_prefix

    STRUCTURED_OUTPUT_REPAIR_SYSTEM_PROMPT = """You repair serialization only.
Return exactly one JSON object that validates against the supplied JSON Schema.
Preserve every recoverable narrative, title, summary, evidence, state delta,
thread, memory, and consistency value from the malformed payload. Do not add,
remove, rewrite, embellish, continue, or reinterpret story content. Fix only
JSON syntax, field names, primitive types, missing required empty arrays, and
schema shape. If narrative_cells are present, preserve each cell value and its
frozen order verbatim while converting only the surrounding JSON shape. Output JSON
only, with no Markdown or explanation."""

    PLANNER_SYSTEM_PROMPT = """You are the internal planning pass of one novel Writer.
Return one ChapterPlan JSON object and nothing else. This is temporary section
planning, not canon, memory, state, or a separate story agent.

You may only allocate the required event IDs and required end-state IDs supplied
by the frozen NarrativeContract and EventExecutionPlan. You must not create a
person, location, item, organization, event, thread, state delta, memory,
background fact, history, relationship, injury, casualty, number, date, or world
rule. Copy IDs exactly. Do not paraphrase IDs.

Use exactly four segments in this order: opening, development, conflict,
resolution. Segment target_chars must sum exactly to SectionBudgetPlan
target_chars. Bind every required event to exactly one segment, preserve event
order, list every required event in required_events, list every required end
state in required_end_states, and preserve all server stop conditions. The
resolution segment lands the required end states. StyleBalanceContract controls
expression only; it may not change event count, structure, or length."""

    PLANNING_WRITER_PROMPT = """
The server-derived ChapterPlan below is mandatory for required event order,
required end states, and stop conditions. Its four segments provide soft structural guidance,
not exact prose quotas. The total
SectionBudgetPlan min_chars/max_chars range remains the authoritative acceptance
boundary. The fifty-two logical-cell targets across ten logical blocks form one
additive Provider drafting allocation whose prose-cell sum equals the
single Provider drafting target. They are not independent acceptance gates; exact
cell shape, nonblank prose, and joined aggregate length are validated by the server.
"Soft" describes server acceptance, not an optional drafting request. Draft every
required beat cell as one complete developed prose sentence near its stated target.
Every required beat cell remains mandatory.
Within the frozen facts, use consecutive cells for action or spatial motion,
immediate sensory/environment/current-character interaction, and an existing
reaction, consequence, or transition. Never answer with a synopsis, a label, a
fragment, or a placeholder.
This response is the sole initial Writer call. Do not request, defer to, or imply
additional first-pass generation for a segment or micro-block.
Complete only the listed existing events. Build existing action, environment,
current-character interaction, and existing emotion toward the server target
before writing terminal end-state evidence. Put terminal evidence in the final
closure, then stop.
Do not create plot to fill length. Length must come from elaborating existing
events, not from new people, background, conflict, history, or world rules.

Return chapter_evidence with exactly one record for each segment 1-4. Each record
contains only the event IDs actually completed in that planned segment. This
evidence is diagnostic and never overrides prose validation.
"""

    SYSTEM_PROMPT = """你是长篇小说 Writer。你收到十一个按优先级隔离的上下文槽位。
NarrativeContract 是本节人物、事实、事件链、时间压力和固定结局的正文硬契约；
StoryBible 是主题与世界规则的最高权威；CanonicalState 是当前事实的唯一权威；
历史记忆只能提供背景，不能覆盖前三者。请围绕 SectionGoal 写一节连续正文。

权威顺序必须遵守：NarrativeContract > StoryBible / CanonicalState > StyleContract。
风格要求若不能在现有事件链内完成，则允许少满足一项风格特征，不允许新增事实。
Style controls expression, not event count and not chapter length.
不得靠新增打斗、亲属、陪同者、数字、日期、伤势或幕后责任人满足风格；不得为了
含蓄、悬念或格式而省略 NarrativeContract 的必要事件和最终状态。

必须严格按 narrative_contract 槽位中的 EventExecutionPlan.order 顺序实际完成事件。
“准备、打算、走向、想要、即将、如果、也许、原本可以”均不算完成；最后一段必须
明确落实人物动作、物品接收者以及所有 required_end_states。

只返回一个严格符合随附 JSON Schema 的对象。正文载荷字段以 schema.required 为准：
要求 narrative_cells 时只能返回 narrative_cells，要求 narrative_text 时只能返回
narrative_text，绝不能同时返回二者，也不得返回旧 narrative_blocks。其余业务字段为 title、section_summary、
event_evidence、end_state_evidence、state_delta、threads_opened、threads_advanced、
threads_resolved、memory_records、consistency_notes、chapter_evidence。

没有确定变化时保持数组为空，不要用 null。state_delta 项形如
{"op":"set","path":"/characters/角色ID/字段","value":"新值",
"evidence":"正文中逐字出现的短句","confidence":0.9}。
故事线对象至少含 id、type、description；memory 对象至少含 id、type、summary。
故事线 type 只能从 mystery、conflict、promise、threat、goal 中选择，status 只能从
open、advancing、resolved、abandoned、stale、needs_attention 中选择；memory type
只能从 event、decision、relationship_change、revelation、promise、consequence 中选择。
这些枚举值必须原样使用英文，不得翻译或另造类别。

state_delta 的每项必须包含 op、path、value、evidence、confidence；path 只能指向
CanonicalState。不得提出 StoryBible 修改。故事线 resolved 必须附正文中可定位的
resolution_evidence。正文之外不要输出解释、Markdown 或思考过程。"""

    REPAIR_SYSTEM_PROMPT = """你不是作者，你是只做局部修改的小说编辑。
最多执行这一次 Repair。你的任务不是重写文章，只能输出 patch JSON。

严格规则：
1. 根对象只能包含 schema_version 和 patches。
2. 每个 patch 只能包含 patch_id 和 patch_text；patch_text 必须是对象且只能包含 schema 指定的三个 beat 键。
3. patch_id 必须逐字复制 provider_patch_requests；不得新增、遗漏或重复。
4. 你无权返回或修改 patch_type、anchor、offset、targets、target_chars、max_chars、
   preserve、purpose、remove_reason、原文 hash 或契约 hash；这些字段由服务端冻结。
5. patch_text 的三个 beat 依次扩写获准的既有动作、环境、已有人物互动或已存在情绪；服务端原样连接为内部 patch_text 字符串。
6. 不新增人物、背景、数字、日期、亲属、伤势、伤亡、世界规则、状态或支线。
7. 不复制整段原文，不输出完整 narrative_text，也不做自报字数。
8. provider_patch_requests 只用于纯长度扩写。仅 patch_text 的 beat 值不得出现 0-9 或
   “零〇一二两三四五六七八九十百千万”中的任何字符；修辞、成语、约数也禁用。
   schema_version 与 patch_id 不受此词法限制。引用现有角色时用代词，数量感改用
   “些、少许、片刻、反复、短暂、微微”等不含数字的词。返回前逐个自检 patch_text 的所有 cell。

禁止输出 narrative_text、state_delta、threads、memory、summary、title、解释、Markdown
或内部分析。"""

    LENGTH_SYSTEM_PROMPT = """
SectionWritingPlan and SectionBudgetPlan are server-owned and mandatory. Follow
the four-segment progression. Write within the min_chars/max_chars range
(for a 900-character request this is 900-1100), complete every required event
and required end state, and do not add characters, background, numbers,
kinship, casualties, injuries, dates, or world rules. Style changes narration,
never the event inventory or final state.
The minimum is a rejection floor, not the writing target. Do not close before
the safe target zone. Put the terminal state in the final closure and stop
immediately afterward. Never continue with another person, background, conflict,
history, relationship, or explanation.
The supplied JSON Schema requires one exact narrative_cells object containing
fifty-two exact, nonempty string beats across ten logical blocks. Every value is
one complete developed prose sentence. Per-block and per-cell targets are soft
steering only. The hard length check counts non-whitespace
characters across the joined prose; never use whitespace to satisfy it.
"""

    REPAIR_LENGTH_PROMPT = """
The server has already selected every operation and placement. Generate prose
only for provider_patch_requests. Patch IDs, order, anchors, and placements are
server-frozen. For every patch, return patch_text as an object containing exactly
the three required beat keys;
each cell must be one complete developed prose beat. The server concatenates the
three values verbatim as patch_text. That joined text must stay within its own hard
min_chars and max_chars bounds. Per-patch target_chars values are advisory; uneven
prose allocation between sibling patches is allowed only inside each sibling's
frozen minimum-maximum band. The payload's aggregate length budget and the final
section min_chars/max_chars range are hard. Do not repeat
or paraphrase another patch, truncate prose automatically, or report a character
count. The server applies deterministic event, end-state, delete, and compact
operations without asking you to copy them.
Each request's three cell_target_chars are mandatory drafting steering even though
individual cell length is not a separate server acceptance gate. Write one complete
developed prose beat in each cell near its supplied target, counting punctuation,
instead of a fragment or terse summary.
Each patch_id const and joined patch length contract in the supplied JSON Schema is
frozen from the matching server request. Returning a missing cell or an undersize,
blank, or oversize joined patch invalidates the entire atomic repair.
Before returning JSON, scan every patch_text beat and remove every glyph matched by
[0-9零〇一二两三四五六七八九十百千万], including rhetorical, approximate,
and idiomatic uses. This lexical rule applies only to patch_text, not
schema_version or patch_id. These pure length expansions have no authorized
numeric content.
"""

    async def plan(self, context: ContextPackage, goal: SectionGoal) -> PlannerResult:
        del goal
        output_schema = json.dumps(
            ChapterPlan.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            response = await llm_client.chat(
                system_prompt=(
                    self.PLANNER_SYSTEM_PROMPT
                    + "\nThe following JSON Schema is the only output contract; "
                    "additionalProperties=false:\n"
                    + output_schema
                ),
                user_prompt=json.dumps(
                    self._planner_payload(context),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                temperature=0.0,
                max_tokens=2048,
                agent_id="author_writer_planner",
                priority="critical",
                response_format={"type": "json_object"},
            )
        except ProviderError as exc:
            self._annotate_provider_failure(
                exc,
                stage="planner",
                primary_calls=1,
                structured_calls=0,
            )
            raise
        try:
            plan = self._parse_plan(response.content)
        except WriterOutputError as exc:
            failure = provider_output_invalid(self._provider_error_config(response))
            raise self._annotate_provider_failure(
                failure,
                stage="planner",
                primary_calls=1,
                structured_calls=0,
            ) from exc
        return PlannerResult(
            plan=plan,
            usage=self._usage(response),
        )

    async def generate(self, context: ContextPackage, goal: SectionGoal) -> WriterResult:
        output_schema = json.dumps(
            self._writer_output_schema(context),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        style_prefix = self._style_prompt_prefix + "\n\n" if self._style_prompt_prefix else ""
        try:
            response = await llm_client.chat(
                system_prompt=(
                    style_prefix
                    + self.SYSTEM_PROMPT
                    + self.LENGTH_SYSTEM_PROMPT
                    + self.PLANNING_WRITER_PROMPT
                    + self._writer_shape_prompt(context)
                    + "\n以下 JSON Schema 是唯一输出契约；additionalProperties=false：\n"
                    + output_schema
                ),
                user_prompt=context.prompt + self._final_directive(context),
                temperature=0.4,
                # Reasoning-capable OpenAI-compatible models may consume hidden/reasoning
                # budget before emitting the JSON candidate. Keep the bounded 8192 ceiling
                # available so valid section prose is not truncated before serialization.
                max_tokens=8192,
                agent_id="author_writer",
                priority="critical",
                response_format={"type": "json_object"},
            )
        except ProviderError as exc:
            self._annotate_provider_failure(
                exc,
                stage="writer",
                primary_calls=1,
                structured_calls=0,
            )
            raise
        usage = self._usage(response)
        try:
            candidate = self._parse(response.content)
        except WriterOutputError:
            try:
                repaired = await self._repair_structured_output(
                    malformed=response.content,
                    output_schema=output_schema,
                    agent_id="author_writer_json_repair",
                    max_tokens=8192,
                )
            except ProviderError as exc:
                self._annotate_provider_failure(
                    exc,
                    stage="writer_json_repair",
                    primary_calls=1,
                    structured_calls=1,
                )
                raise
            usage = self._merge_usage(usage, self._usage(repaired))
            try:
                candidate = self._parse(repaired.content)
            except WriterOutputError as exc:
                failure = provider_output_invalid(
                    self._provider_error_config(repaired)
                )
                raise self._annotate_provider_failure(
                    failure,
                    stage="writer_json_repair",
                    primary_calls=1,
                    structured_calls=1,
                ) from exc
            recovered_contract_pass, _recovered_contract_codes = (
                self._writer_primary_contract(repaired.content, context)
            )
            if not recovered_contract_pass:
                failure = provider_output_invalid(
                    self._provider_error_config(repaired)
                )
                raise self._annotate_provider_failure(
                    failure,
                    stage="writer_json_repair",
                    primary_calls=1,
                    structured_calls=1,
                )
            (
                recovered_block_lengths,
                recovered_cell_lengths,
                recovered_sentence_boundaries,
            ) = self._writer_structure_metrics(repaired.content)
            return WriterResult(
                candidate=candidate,
                usage=usage,
                structured_output_repair_count=1,
                primary_output_contract_pass=False,
                audit_codes=["WRITER_FORMAT_RECOVERY_USED"],
                writer_block_nonspace_lengths=recovered_block_lengths,
                writer_cell_nonspace_lengths=recovered_cell_lengths,
                writer_cell_sentence_boundary_counts=(
                    recovered_sentence_boundaries
                ),
                **self._provider_receipt(repaired),
            )
        primary_contract_pass, primary_codes = self._writer_primary_contract(
            response.content,
            context,
        )
        if not primary_contract_pass and primary_codes != [
            "WRITER_BLOCK_TOTAL_OUT_OF_RANGE"
        ]:
            failure = provider_output_invalid(self._provider_error_config(response))
            raise self._annotate_provider_failure(
                failure,
                stage="writer",
                primary_calls=1,
                structured_calls=0,
            )
        block_lengths, cell_lengths, sentence_boundaries = (
            self._writer_structure_metrics(response.content)
        )
        return WriterResult(
            candidate=candidate,
            usage=usage,
            primary_output_contract_pass=primary_contract_pass,
            audit_codes=primary_codes,
            writer_block_nonspace_lengths=block_lengths,
            writer_cell_nonspace_lengths=cell_lengths,
            writer_cell_sentence_boundary_counts=sentence_boundaries,
            **self._provider_receipt(response),
        )

    async def repair(
        self, candidate: WriterCandidate, plan: RepairPlan
    ) -> WriterResult:
        output_schema = json.dumps(
            self._repair_output_schema(plan),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            response = await llm_client.chat(
                system_prompt=(
                    self.REPAIR_SYSTEM_PROMPT
                    + self.REPAIR_LENGTH_PROMPT
                    + "\n以下 JSON Schema 是唯一输出契约；additionalProperties=false：\n"
                    + output_schema
                ),
                user_prompt=json.dumps(
                    repair_patch_prompt_payload(plan, candidate.narrative_text),
                    ensure_ascii=False,
                    indent=2,
                ),
                temperature=0.0,
                max_tokens=4096,
                agent_id="author_writer_repair",
                priority="critical",
                response_format={"type": "json_object"},
            )
        except ProviderError as exc:
            self._annotate_provider_failure(
                exc,
                stage="repair",
                primary_calls=1,
                structured_calls=0,
            )
            raise
        usage = self._usage(response)
        content = response.content
        try:
            provider_patches = self._parse_provider_repair_patches(content, plan)
        except WriterOutputError:
            try:
                repaired = await self._repair_structured_output(
                    malformed=content,
                    output_schema=output_schema,
                    agent_id="author_writer_patch_json_repair",
                    max_tokens=4096,
                )
            except ProviderError as exc:
                self._annotate_provider_failure(
                    exc,
                    stage="repair_json_repair",
                    primary_calls=1,
                    structured_calls=1,
                )
                raise
            usage = self._merge_usage(usage, self._usage(repaired))
            content = repaired.content
            try:
                provider_patches = self._parse_provider_repair_patches(
                    content,
                    plan,
                )
            except WriterOutputError as exc:
                failure = provider_output_invalid(
                    self._provider_error_config(repaired)
                )
                raise self._annotate_provider_failure(
                    failure,
                    stage="repair_json_repair",
                    primary_calls=1,
                    structured_calls=1,
                ) from exc
            structured_output_repair_count = 1
            receipt_response = repaired
        else:
            structured_output_repair_count = 0
            receipt_response = response
        ignored_fields = self._repair_ignored_fields(content)
        return WriterResult(
            candidate=candidate,
            usage=usage,
            structured_output_repair_count=structured_output_repair_count,
            **self._provider_receipt(receipt_response),
            ignored_fields=ignored_fields,
            audit_codes=(
                ["REPAIR_EXTRA_FIELD_IGNORED"] if ignored_fields else []
            ),
            provider_repair_patches=provider_patches,
        )

    async def _repair_structured_output(
        self,
        *,
        malformed: str,
        output_schema: str,
        agent_id: str,
        max_tokens: int,
    ):
        """Perform the one permitted format-only recovery call.

        This is not a full Writer retry: it receives neither the frozen story
        context nor permission to generate new prose, and the malformed value
        is never written to an error, receipt, or transaction journal.
        """

        return await llm_client.chat(
            system_prompt=(
                self.STRUCTURED_OUTPUT_REPAIR_SYSTEM_PROMPT
                + "\nThe following JSON Schema is authoritative:\n"
                + output_schema
            ),
            user_prompt=json.dumps(
                {"malformed_output": malformed},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            temperature=0.0,
            max_tokens=max_tokens,
            agent_id=agent_id,
            priority="critical",
            response_format={"type": "json_object"},
        )

    @staticmethod
    def _join_writer_cells(
        cells: object,
    ) -> tuple[str, list[str], list[str]]:
        """Validate the 52 provider-only cells and join without rewriting prose."""

        if not isinstance(cells, dict) or set(cells) != set(_WRITER_CELL_NAMES):
            raise WriterOutputError(
                "Writer narrative cells do not match the frozen shape"
            )
        block_values: list[str] = []
        cell_values: list[str] = []
        for block_name in _WRITER_BLOCK_NAMES:
            cell_names = _WRITER_BLOCK_CELL_NAMES[block_name]
            ordered_cells: list[str] = []
            for cell_name in cell_names:
                value = cells.get(cell_name)
                if not isinstance(value, str) or not value.strip():
                    raise WriterOutputError(
                        "Writer narrative cells do not match the frozen shape"
                    )
                ordered_cells.append(value)
            cell_values.extend(ordered_cells)
            block_values.append("".join(ordered_cells))
        return "\n\n".join(block_values), block_values, cell_values

    @staticmethod
    def _join_legacy_writer_blocks(
        blocks: object,
    ) -> tuple[str, list[str], list[str]]:
        """Read the superseded ten-string envelope for stored fixture compatibility."""

        if (
            not isinstance(blocks, dict)
            or set(blocks) != set(_WRITER_BLOCK_NAMES)
            or any(
                not isinstance(blocks.get(name), str) or not blocks[name].strip()
                for name in _WRITER_BLOCK_NAMES
            )
        ):
            raise WriterOutputError(
                "Writer narrative blocks do not match the frozen shape"
            )
        block_values = [blocks[name] for name in _WRITER_BLOCK_NAMES]
        return "\n\n".join(block_values), block_values, []

    @staticmethod
    def _writer_structure_metrics(
        content: str,
    ) -> tuple[list[int], list[int], list[int]]:
        """Return prose-free structured-shape diagnostics for acceptance receipts."""

        try:
            payload = parse_llm_json((content or "").strip())
            if not isinstance(payload, dict):
                return [], [], []
            _joined, blocks, cells = AuthorWriter._join_writer_cells(
                payload.get("narrative_cells")
            )
        except (json.JSONDecodeError, WriterOutputError):
            return [], [], []
        return (
            [sum(not char.isspace() for char in value) for value in blocks],
            [sum(not char.isspace() for char in value) for value in cells],
            [
                sum(char in _WRITER_SENTENCE_BOUNDARIES for char in value)
                for value in cells
            ],
        )

    @staticmethod
    def _parse(content: str) -> WriterCandidate:
        text = (content or "").strip()
        try:
            payload = parse_llm_json(text)
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer returned invalid JSON") from exc
        if isinstance(payload, dict) and "narrative_cells" in payload:
            if "narrative_text" in payload or "narrative_blocks" in payload:
                raise WriterOutputError(
                    "Writer returned ambiguous narrative prose fields"
                )
            joined, _block_values, _cell_values = AuthorWriter._join_writer_cells(
                payload.get("narrative_cells")
            )
            payload = dict(payload)
            payload.pop("narrative_cells", None)
            payload["narrative_text"] = joined
        elif isinstance(payload, dict) and "narrative_blocks" in payload:
            if "narrative_text" in payload:
                raise WriterOutputError(
                    "Writer returned ambiguous narrative prose fields"
                )
            joined, _block_values, _cell_values = (
                AuthorWriter._join_legacy_writer_blocks(
                    payload.get("narrative_blocks")
                )
            )
            payload = dict(payload)
            payload.pop("narrative_blocks", None)
            payload["narrative_text"] = joined
        try:
            return WriterCandidate.model_validate(payload)
        except Exception as exc:
            raise WriterOutputError(f"WriterCandidate validation failed: {exc}") from exc

    @staticmethod
    def _parse_plan(content: str) -> ChapterPlan:
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer planner returned invalid JSON") from exc
        try:
            return ChapterPlan.model_validate(payload)
        except Exception as exc:
            raise WriterOutputError(
                f"ChapterPlan validation failed: {exc}"
            ) from exc

    @staticmethod
    def _parse_provider_repair_patches(
        content: str,
        plan: RepairPlan | None = None,
    ) -> ProviderRepairPatchSet:
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer repair returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WriterOutputError("Writer repair must return a JSON object")
        raw_patches = payload.get("patches", [])
        if isinstance(raw_patches, dict):
            raw_patches = [raw_patches]
        if not isinstance(raw_patches, list):
            raise WriterOutputError("Writer repair patches must be a JSON array")
        provider_templates = [
            template
            for template in getattr(plan, "patch_templates", [])
            if template.provider_text_required
        ]
        if plan is not None and len(raw_patches) != len(provider_templates):
            raise WriterOutputError(
                "Writer repair patches do not match the frozen shape"
            )
        patches: list[dict[str, str | None]] = []
        for raw in raw_patches:
            if not isinstance(raw, dict):
                raise WriterOutputError(
                    "Writer repair patches do not match the frozen shape"
                )
            patch_text = raw.get("patch_text")
            if isinstance(patch_text, dict):
                if set(patch_text) != set(_REPAIR_CELL_NAMES):
                    raise WriterOutputError(
                        "Writer repair cells do not match the frozen shape"
                    )
                ordered_cells: list[str] = []
                for cell_name in _REPAIR_CELL_NAMES:
                    value = patch_text.get(cell_name)
                    if not isinstance(value, str) or not value.strip():
                        raise WriterOutputError(
                            "Writer repair cells do not match the frozen shape"
                        )
                    ordered_cells.append(value)
                normalized_text: str | None = "".join(ordered_cells)
            elif plan is None and isinstance(patch_text, str):
                # Persisted fixtures use the internal scalar representation.
                normalized_text = patch_text
            else:
                raise WriterOutputError(
                    "Writer repair cells do not match the frozen shape"
                )
            patches.append(
                {
                    "patch_id": raw.get("patch_id"),
                    "patch_text": normalized_text,
                }
            )
        try:
            return ProviderRepairPatchSet.model_validate(
                {
                    "schema_version": payload.get("schema_version", 1),
                    "patches": patches,
                }
            )
        except Exception as exc:
            raise WriterOutputError(
                f"Writer repair patch validation failed: {exc}"
            ) from exc

    @staticmethod
    def _parse_repair_patches(content: str) -> RepairPatchSet:
        """Legacy parser for persisted fixtures and compatibility tests only."""
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer repair returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WriterOutputError("Writer repair must return a JSON object")
        raw_patches = payload.get("patches", [])
        if isinstance(raw_patches, dict):
            raw_patches = [raw_patches]
        if not isinstance(raw_patches, list):
            raw_patches = []
        patches: list[dict] = []
        allowed_patch_fields = {
            "patch_id",
            "patch_type",
            "anchor",
            "patch_text",
            "target_events",
            "target_end_states",
            "max_chars",
            "preserve",
            "target_chars",
            "purpose",
            "remove_reason",
            "max_remove_chars",
        }
        for raw in raw_patches:
            if not isinstance(raw, dict):
                continue
            item = {key: raw[key] for key in allowed_patch_fields if key in raw}
            anchor = item.get("anchor")
            if isinstance(anchor, str):
                item["anchor"] = {"before_text": anchor, "after_text": ""}
            elif isinstance(anchor, dict):
                item["anchor"] = {
                    key: anchor[key]
                    for key in ("before_text", "after_text", "start", "end")
                    if key in anchor
                }
            for key in ("target_events", "target_end_states", "preserve"):
                value = item.get(key, [])
                if value is None:
                    item[key] = []
                elif not isinstance(value, list):
                    item[key] = [value]
            if isinstance(item.get("patch_type"), str):
                item["patch_type"] = item["patch_type"].strip().lower()
            patches.append(item)
        try:
            return RepairPatchSet.model_validate(
                {
                    "schema_version": payload.get("schema_version", 1),
                    "patches": patches,
                }
            )
        except Exception as exc:
            raise WriterOutputError(
                f"Writer repair patch validation failed: {exc}"
            ) from exc

    @staticmethod
    def _repair_ignored_fields(content: str) -> list[str]:
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        ignored = {
            key for key in payload if key not in {"schema_version", "patches"}
        }
        raw_patches = payload.get("patches", [])
        if isinstance(raw_patches, dict):
            raw_patches = [raw_patches]
        allowed_patch_fields = {"patch_id", "patch_text"}
        if isinstance(raw_patches, list):
            for index, patch in enumerate(raw_patches):
                if not isinstance(patch, dict):
                    continue
                ignored.update(
                    f"patches[{index}].{key}"
                    for key in patch
                    if key not in allowed_patch_fields
                )
        return sorted(ignored)

    @staticmethod
    def _writer_output_schema(context: ContextPackage) -> dict:
        """Steer 52 explicit prose cells while keeping aggregate length authoritative."""

        schema = WriterCandidate.model_json_schema()
        budget = context.section_budget_plan
        profiles = AuthorWriter._writer_block_profiles(context)
        if budget is None or not profiles:
            return schema
        drafting_targets = AuthorWriter._writer_drafting_targets(context)
        roles_by_count = {
            3: (
                "existing action or spatial motion",
                "immediate perception, environment, or current-character interaction",
                "existing reaction, consequence, or transition",
            ),
            4: (
                "existing action or spatial motion",
                "immediate spatial or environmental detail",
                "current-character interaction or existing emotion",
                "existing reaction, consequence, or transition",
            ),
            6: (
                "existing action or spatial motion",
                "immediate spatial or environmental detail",
                "current sensory perception",
                "current-character interaction",
                "existing emotion or physical reaction",
                "existing consequence or transition",
            ),
        }
        cell_properties: dict[str, dict] = {}
        block_map: dict[str, dict] = {}
        for name, group_name, soft_min, soft_target, soft_max in profiles:
            cell_names = _WRITER_BLOCK_CELL_NAMES[name]
            cell_targets = drafting_targets[name]
            block_map[name] = {
                "cells": list(cell_names),
                "group": group_name,
                "numeric_block_quota_exposed": False,
            }
            for ordinal, (cell_name, cell_target, role) in enumerate(
                zip(
                    cell_names,
                    cell_targets,
                    roles_by_count[len(cell_names)],
                    strict=True,
                ),
                start=1,
            ):
                steering = {
                    "drafting_requirement": "mandatory",
                    "acceptance_scope": "joined_aggregate_only",
                    "block_name": name,
                    "block_group": group_name,
                    "cell_ordinal": ordinal,
                    "cell_count": len(cell_names),
                    "soft_sentence_count": 1,
                    "soft_target_nonwhitespace_chars": cell_target,
                    "punctuation_included": True,
                }
                cell_properties[cell_name] = {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        f"Block {name}, prose beat {ordinal} of {len(cell_names)}: "
                        f"{role}. Write one complete developed sentence-sized "
                        f"prose beat near the soft target of {cell_target} "
                        "non-whitespace Unicode characters, including punctuation. "
                        "Never return a label, fragment, synopsis, outline, or "
                        "placeholder."
                    ),
                    "x-generation-steering": steering,
                }
        schema["properties"].pop("narrative_text", None)
        schema["properties"]["narrative_cells"] = {
            "type": "object",
            "additionalProperties": False,
            "required": list(_WRITER_CELL_NAMES),
            "description": (
                "Fifty-two consecutive sentence-sized prose beats spanning ten "
                "logical blocks. Every cell is one nonempty prose string. "
                "Cell targets form one additive soft Provider "
                "drafting allocation; logical-block membership carries no separate "
                "numeric quota. After "
                "joining cells in the required order, the server hard-validates "
                f"{int(budget.min_chars)}-{int(budget.max_chars)} "
                "non-whitespace Unicode characters."
            ),
            "x-aggregate-length-contract": {
                "count": "non-whitespace Unicode characters",
                "min": int(budget.min_chars),
                "drafting_target": AuthorWriter._writer_provider_drafting_target(
                    context
                ),
                "max": int(budget.max_chars),
                "min_and_max_server_enforced": True,
                "drafting_target_server_enforced": False,
            },
            "x-provider-calibration": {
                "logical_cell_count": len(_WRITER_CELL_NAMES),
                "total_prose_leaf_count": len(_WRITER_CELL_NAMES),
                "soft_target_per_prose_cell_min": min(
                    target for values in drafting_targets.values() for target in values
                ),
                "soft_target_per_prose_cell_max": max(
                    target for values in drafting_targets.values() for target in values
                ),
                "additive_soft_target_sum": (
                    AuthorWriter._writer_provider_drafting_target(context)
                ),
                "calibration_targets_are_additive": True,
            },
            "x-block-map": block_map,
            "properties": cell_properties,
        }
        required = list(schema.get("required") or [])
        schema["required"] = [
            "narrative_cells" if item == "narrative_text" else item
            for item in required
        ]
        return schema

    @staticmethod
    def _writer_block_profiles(
        context: ContextPackage,
    ) -> list[tuple[str, str, int, int, int]]:
        """Split each planned segment into stable soft micro-block budgets."""

        budget = context.section_budget_plan
        segments = list(getattr(budget, "segments", []) or [])
        group_names = tuple(group_name for group_name, _ in _WRITER_BLOCK_GROUPS)
        if (
            budget is None
            or len(segments) != len(_WRITER_BLOCK_GROUPS)
            or tuple(str(item.name) for item in segments) != group_names
        ):
            return []

        weights = [int(item.budget) for item in segments]
        safe_floor = max(int(budget.min_chars), int(budget.target_chars) - 50)
        minimum_reduction = AuthorWriter._allocate_proportional(
            int(budget.target_chars) - safe_floor,
            weights,
        )
        segment_minimums = [
            int(segment.budget) - reduction
            for segment, reduction in zip(
                segments,
                minimum_reduction,
                strict=True,
            )
        ]
        maximum_slack = AuthorWriter._allocate_proportional(
            int(budget.max_chars) - int(budget.target_chars),
            weights,
        )
        segment_maxima = [
            int(segment.budget) + slack
            for segment, slack in zip(
                segments,
                maximum_slack,
                strict=True,
            )
        ]

        profiles: list[tuple[str, str, int, int, int]] = []
        for (
            segment,
            segment_minimum,
            segment_maximum,
            (group_name, block_names),
        ) in zip(
            segments,
            segment_minimums,
            segment_maxima,
            _WRITER_BLOCK_GROUPS,
            strict=True,
        ):
            equal_weights = [1] * len(block_names)
            minimums = AuthorWriter._allocate_proportional(
                segment_minimum,
                equal_weights,
            )
            targets = AuthorWriter._allocate_proportional(
                int(segment.budget),
                equal_weights,
            )
            maxima = AuthorWriter._allocate_proportional(
                segment_maximum,
                equal_weights,
            )
            profiles.extend(
                (block_name, group_name, soft_min, soft_target, soft_max)
                for block_name, soft_min, soft_target, soft_max in zip(
                    block_names,
                    minimums,
                    targets,
                    maxima,
                    strict=True,
                )
            )
        return profiles

    @staticmethod
    def _writer_primary_contract(
        content: str,
        context: ContextPackage,
    ) -> tuple[bool, list[str]]:
        """Audit exact shape, nonblank chunks, and hard joined total length."""

        schema = AuthorWriter._writer_output_schema(context)
        cell_schema = schema.get("properties", {}).get("narrative_cells")
        if not isinstance(cell_schema, dict):
            return True, []
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError:
            return False, ["WRITER_BLOCKS_INVALID_JSON"]
        if not isinstance(payload, dict):
            return False, ["WRITER_BLOCKS_MISSING"]
        if "narrative_cells" in payload and (
            "narrative_text" in payload or "narrative_blocks" in payload
        ):
            return False, ["WRITER_BLOCKS_AMBIGUOUS"]
        cells = payload.get("narrative_cells")
        cell_names = tuple(cell_schema.get("required") or [])
        if not isinstance(cells, dict) or set(cells) != set(cell_names):
            return False, ["WRITER_BLOCKS_MISSING"]
        try:
            joined, _blocks, _cells = AuthorWriter._join_writer_cells(cells)
        except WriterOutputError:
            return False, ["WRITER_BLOCKS_INVALID"]
        actual = sum(not char.isspace() for char in joined)
        budget = context.section_budget_plan
        if actual < int(budget.min_chars) or actual > int(budget.max_chars):
            return False, ["WRITER_BLOCK_TOTAL_OUT_OF_RANGE"]
        return True, []

    @staticmethod
    def _allocate_proportional(total: int, weights: list[int]) -> list[int]:
        """Stable largest-remainder allocation for exact prompt-only totals."""

        weight_total = sum(weights)
        if total < 0 or not weights or weight_total <= 0:
            raise ValueError("invalid proportional allocation")
        allocations = [total * weight // weight_total for weight in weights]
        remainder = total - sum(allocations)
        order = sorted(
            range(len(weights)),
            key=lambda index: (
                -(total * weights[index] % weight_total),
                index,
            ),
        )
        for index in order[:remainder]:
            allocations[index] += 1
        return allocations

    @staticmethod
    def _sentence_targets(
        target_chars: int,
        *,
        count: int | None = None,
    ) -> list[int]:
        """Return prompt-only sentence targets with an exact aggregate total."""

        sentence_count = (
            max(1, (target_chars + 39) // 40)
            if count is None
            else count
        )
        if sentence_count <= 0:
            raise ValueError("sentence count must be positive")
        return AuthorWriter._allocate_proportional(
            target_chars,
            [1] * sentence_count,
        )

    @staticmethod
    def _writer_drafting_targets(
        context: ContextPackage,
    ) -> dict[str, list[int]]:
        """Return one physically additive soft allocation across all prose leaves."""

        profiles = AuthorWriter._writer_block_profiles(context)
        leaf_targets = AuthorWriter._writer_leaf_targets(context)
        if not profiles or not leaf_targets:
            return {}
        targets: dict[str, list[int]] = {}
        for block_name, *_profile in profiles:
            targets[block_name] = [
                sum(leaf_targets[cell_name])
                for cell_name in _WRITER_BLOCK_CELL_NAMES[block_name]
            ]
        if sum(sum(values) for values in targets.values()) != (
            AuthorWriter._writer_provider_drafting_target(context)
        ):
            raise ValueError("writer drafting allocation does not match its target")
        return targets

    @staticmethod
    def _writer_leaf_targets(
        context: ContextPackage,
    ) -> dict[str, tuple[int, ...]]:
        if context.section_budget_plan is None:
            return {}
        drafting_target = AuthorWriter._writer_provider_drafting_target(context)
        if drafting_target < _WRITER_TOTAL_PROSE_LEAF_COUNT:
            raise ValueError("writer drafting target cannot cover every prose leaf")
        # Put the one-character remainder toward later beats so the frozen terminal
        # cell is never the shortest drafting obligation.
        allocated = list(
            reversed(
                AuthorWriter._allocate_proportional(
                    drafting_target,
                    [1] * _WRITER_TOTAL_PROSE_LEAF_COUNT,
                )
            )
        )
        cursor = 0
        targets: dict[str, tuple[int, ...]] = {}
        for cell_name in _WRITER_CELL_NAMES:
            targets[cell_name] = (allocated[cursor],)
            cursor += 1
        if cursor != len(allocated) or sum(map(sum, targets.values())) != drafting_target:
            raise ValueError("writer prose-leaf allocation does not match its target")
        return targets

    @staticmethod
    def _writer_provider_drafting_target(context: ContextPackage) -> int:
        budget = context.section_budget_plan
        if budget is None:
            return 1
        return max(
            int(budget.min_chars),
            min(
                int(budget.max_chars),
                max(
                    int(budget.target_chars),
                    int(budget.max_chars) - _WRITER_PROVIDER_DRAFTING_HEADROOM,
                ),
            ),
        )

    @staticmethod
    def _writer_shape_prompt(context: ContextPackage) -> str:
        budget = context.section_budget_plan
        profiles = AuthorWriter._writer_block_profiles(context)
        if budget is None or not profiles:
            return ""
        drafting_targets = AuthorWriter._writer_drafting_targets(context)
        provider_drafting_target = AuthorWriter._writer_provider_drafting_target(
            context
        )
        block_lines = "\n".join(
            (
                f"- {name} ({group_name}): cells "
                + ", ".join(
                    f"{cell_name}≈{cell_target}"
                    for cell_name, cell_target in zip(
                        _WRITER_BLOCK_CELL_NAMES[name],
                        drafting_targets[name],
                        strict=True,
                    )
                )
                + " including punctuation"
            )
            for name, group_name, _soft_min, _soft_target, _soft_max in profiles
        )
        return f"""
For this call, the supplied schema replaces narrative_text with the provider-only
narrative_cells object. Return exactly these fifty-two keys in order:
{", ".join(_WRITER_CELL_NAMES)}. They are consecutive sentence-sized prose beats
of one continuous scene, not summaries or alternatives. Do not include cell labels
in the prose, repeat material between cells, or also return narrative_text or
narrative_blocks. The server concatenates cells within each logical block directly,
then joins the ten blocks with paragraph breaks, without rewriting any value.
Every one of the fifty-two values must be a nonblank string containing one complete,
distinct, developed prose sentence near its displayed target. Objects, arrays,
fragments, summaries, labels, outlines, and placeholders are invalid.
The fifty-two scalar-cell targets below form one additive Provider drafting
allocation. Their prose-cell sum is exactly {provider_drafting_target}
characters; logical blocks carry no separate numeric quotas. Uneven lengths are
accepted when every cell is nonblank and the joined prose is within the hard aggregate range of
{int(budget.min_chars)}-{int(budget.max_chars)} non-whitespace Unicode characters.
"Soft" describes only that joined-aggregate acceptance scope; it does not make the
drafting allocation optional. Every resulting cell beat must be complete prose,
never a fragment, summary, label, outline, or placeholder.
Using only authorized facts, carry existing action or spatial motion, immediate
sensory/environment or current-character interaction, then an existing reaction,
consequence, or transition. Do not emit terminal end-state evidence in the first
fifty-one cells. Only r2u4 may write decisive action, concrete recipient/end-state
evidence, and brief closure; stop immediately after it.

The single Provider drafting target is {provider_drafting_target} characters. Every
displayed scalar-cell target is one component of that
exact additive sum, not an independent acceptance gate. The joined hard aggregate
range remains authoritative.
Logical-block membership and additive Provider drafting allocation (characters are
Unicode code points, not tokens; no separate numeric block quota is exposed):
{block_lines}
Before emitting JSON, check all fifty-two string values are present, nonblank, and
complete sentences, then count
the joined prose as one section. Continue only an existing scene beat if the
aggregate has not reached the hard minimum; never add facts merely to balance one
soft cell or block target.
"""

    @staticmethod
    def _repair_output_schema(plan: RepairPlan) -> dict:
        """Expose exact provider-text bounds without transferring patch authority."""

        schema = ProviderRepairPatchSet.model_json_schema()
        provider_templates = [
            template
            for template in getattr(plan, "patch_templates", [])
            if template.provider_text_required
        ]
        if not provider_templates:
            return schema
        schema["properties"]["schema_version"] = {
            "type": "integer",
            "const": 1,
            "default": 1,
        }
        schema["required"] = ["schema_version", "patches"]
        prefix_items: list[dict] = []
        for template in provider_templates:
            cell_targets = AuthorWriter._sentence_targets(
                template.target_chars,
                count=len(_REPAIR_CELL_NAMES),
            )
            prefix_items.append(
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["patch_id", "patch_text"],
                    "properties": {
                        "patch_id": {
                            "type": "string",
                            "const": template.patch_id,
                        },
                        "patch_text": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": list(_REPAIR_CELL_NAMES),
                            "description": (
                                "Three consecutive, number-free prose beats. The "
                                "server joins them verbatim in required order. The "
                                f"joined text has hard minimum {template.min_chars}, "
                                f"soft target {template.target_chars}, and hard "
                                f"maximum {template.max_chars} non-whitespace "
                                "Unicode characters."
                            ),
                            "x-joined-length-contract": {
                                "count": "non-whitespace Unicode characters",
                                "min": template.min_chars,
                                "target": template.target_chars,
                                "max": template.max_chars,
                                "minimum_is_hard": True,
                                "target_is_advisory": True,
                                "maximum_is_hard": True,
                            },
                            "properties": {
                                cell_name: {
                                    "type": "string",
                                    "minLength": 1,
                                    "pattern": (
                                        "^[^0-9零〇一二两三四五六七八九十百千万]*$"
                                    ),
                                    "description": (
                                        "One complete developed, number-free prose "
                                        f"beat near the soft target of {cell_target} "
                                        "non-whitespace Unicode characters including "
                                        "punctuation. Do not return a fragment, label, "
                                        "summary, or placeholder."
                                    ),
                                    "x-generation-steering": {
                                        "drafting_requirement": "mandatory",
                                        "acceptance_scope": "joined_patch_bounds",
                                        "soft_target_nonwhitespace_chars": (
                                            cell_target
                                        ),
                                        "punctuation_included": True,
                                    },
                                }
                                for cell_name, cell_target in zip(
                                    _REPAIR_CELL_NAMES,
                                    cell_targets,
                                    strict=True,
                                )
                            },
                        },
                    },
                }
            )
        schema["properties"]["patches"] = {
            "type": "array",
            "minItems": len(provider_templates),
            "maxItems": len(provider_templates),
            "prefixItems": prefix_items,
            "items": False,
        }
        return schema

    @staticmethod
    def _final_directive(context: ContextPackage) -> str:
        budget_plan = context.section_budget_plan
        if budget_plan is None:
            return ""
        drafting_targets = AuthorWriter._writer_drafting_targets(context)
        provider_drafting_target = AuthorWriter._writer_provider_drafting_target(
            context
        )
        block_lines = "\n".join(
            (
                f"- {name}（{group_name}）：必填单元 "
                + "、".join(
                    f"{cell_name}≈{cell_target}"
                    for cell_name, cell_target in zip(
                        _WRITER_BLOCK_CELL_NAMES[name],
                        drafting_targets[name],
                        strict=True,
                    )
                )
            )
            for name, group_name, _soft_min, _soft_target, _soft_max in (
                AuthorWriter._writer_block_profiles(context)
            )
        )
        balance = budget_plan.style_balance_contract
        chapter_plan = context.chapter_plan
        plan_lines = ""
        if chapter_plan is not None:
            rendered_segments = [
                (
                    f"Segment {segment.order}: 目标={segment.purpose}; "
                    f"事件={json.dumps(segment.events, ensure_ascii=False)}"
                )
                for segment in sorted(
                    chapter_plan.segments,
                    key=lambda item: item.order,
                )
            ]
            plan_lines = (
                "\n## 你的章节计划\n"
                + "\n".join(rendered_segments)
                + "\nrequired_end_states="
                + json.dumps(
                    chapter_plan.required_end_states,
                    ensure_ascii=False,
                )
                + "\nstop_condition="
                + json.dumps(
                    chapter_plan.stop_condition,
                    ensure_ascii=False,
                )
                + "\n满足 stop_condition 后立即停止。\n"
            )
        return (
            plan_lines
            + "\n\n## 服务端最终执行令（输出前必须逐项自检）\n"
            f"五十二个单元连接后的 Provider 写作目标 {provider_drafting_target} 字，硬接受区间 "
            f"{budget_plan.min_chars}-{budget_plan.max_chars} 字。\n"
            "五十二个单元的值都必须是非空字符串，每个值写一个完整、展开且彼此不同的"
            "正文句子，并贴近上列软目标。全部单元目标按实际拼接长度相加恰好为 "
            f"{provider_drafting_target}，但仍不改变事件、终态或硬接受区间。\n"
            "以下五十二个 narrative_cells 必须按键名顺序自然衔接并组成十个逻辑块；"
            "单元目标是同一套可相加的 Provider 写作分配，十个逻辑块不另设数值"
            "配额。每个单元"
            "必须非空，硬长度条件只对连接后的非空白"
            "正文总量生效：\n"
            f"{block_lines}\n"
            "先在既有事件内部扩写动作、环境、当前人物互动和已有情绪，目标进入"
            f"约 {max(budget_plan.min_chars, provider_drafting_target - 50)}-"
            f"{provider_drafting_target} 字写作区后，再在最后收束段明确落实全部 "
            "required_end_states；终态证据后立即结束。最低字数只是拒绝下限，不是"
            "写作目标，也不得提前用终态收口。停止时必须已完成全部必要事件和全部"
            "最终状态。不得超过 "
            f"{budget_plan.max_chars} 字；不得在结束后增加新人物、背景、冲突、历史、"
            "关系或解释。\n"
            f"风格平衡：{balance.instruction}\n"
            f"限制：{'；'.join(balance.limits)}。\n"
            f"禁止：{'；'.join(balance.forbidden)}。\n"
            "如果尚未进入目标安全区，只能扩写已有动作、环境、已有人物互动或已存在"
            "情绪。不要创造新的剧情来填充长度。禁止用新人物、新背景、新冲突或"
            "新事实补字数。不要输出、自报或猜测统计字数。\n"
            "FINAL OUTPUT LOCK: Return exactly the fifty-two named narrative_cells "
            "keys in order. Every value must be one nonblank string containing one "
            "distinct, complete, developed prose sentence near its target. Return "
            "no objects or arrays as cell values and no narrative_text or "
            "narrative_blocks field. Cell "
            f"targets form one additive soft allocation totaling {provider_drafting_target}; "
            "logical blocks carry no separate numeric quotas. The joined "
            f"aggregate must be {budget_plan.min_chars}-{budget_plan.max_chars} "
            "non-whitespace Unicode characters.\n"
            "最终单元锁：五十二个 narrative_cells 的每个值都必须是一个完整且充分"
            "展开的句级正文拍点，并贴近上列含标点软目标；依次只承载既有动作或空间"
            "移动、即时感官或环境、当前人物互动、已有反应或后果衔接。禁止用片语、"
            "概述、提纲、标签或占位代替。所有五十二个单元都必须是字符串，不得返回"
            "对象或数组。"
            "“软”只表示服务端不会按单元或单块字数"
            "拒绝，不表示生成要求可以忽略。前面五十一个单元不得给出终态证据；"
            "只在 r2u4 写明决定性动作、明确接收者或终态证据和简短收束，证据之后"
            "立即停止。"
        )

    @staticmethod
    def _planner_payload(context: ContextPackage) -> dict:
        narrative_contract = (
            context.narrative_contract.model_dump(mode="json")
            if context.narrative_contract
            else {}
        )
        event_plan = (
            context.event_execution_plan.model_dump(mode="json")
            if context.event_execution_plan
            else {}
        )
        budget_plan = (
            context.section_budget_plan.model_dump(mode="json")
            if context.section_budget_plan
            else {}
        )
        style_balance = (
            context.section_budget_plan.style_balance_contract.model_dump(
                mode="json"
            )
            if context.section_budget_plan
            else {}
        )
        return {
            "story_bible": context.slots.get("story_bible", ""),
            "canonical_state": context.slots.get("canonical_state", ""),
            "narrative_contract": narrative_contract,
            "event_execution_plan": event_plan,
            "section_budget_plan": budget_plan,
            "style_balance_contract": style_balance,
        }

    @staticmethod
    def _usage(response) -> dict[str, int]:
        prompt = int(getattr(response, "usage_prompt_tokens", 0) or 0)
        completion = int(getattr(response, "usage_completion_tokens", 0) or 0)
        cached = int(getattr(response, "usage_cached_tokens", 0) or 0)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cached_tokens": cached,
            "total_tokens": prompt + completion,
        }

    @staticmethod
    def _provider_receipt(response) -> dict[str, str]:
        return {
            "provider": str(getattr(response, "provider", "") or ""),
            "provider_model": str(getattr(response, "model", "") or ""),
            "provider_source": str(
                getattr(response, "provider_source", "") or ""
            ),
            "provider_config_fingerprint": str(
                getattr(response, "provider_config_fingerprint", "") or ""
            ),
        }

    @staticmethod
    def _provider_error_config(response):
        receipt = getattr(response, "provider_runtime_receipt", None)
        if isinstance(receipt, ProviderRuntimeReceipt):
            return receipt
        fingerprint = str(
            getattr(response, "provider_config_fingerprint", "") or ""
        )
        if fingerprint:
            return ProviderRuntimeReceipt(
                provider=str(getattr(response, "provider", "") or ""),
                model=str(getattr(response, "model", "") or ""),
                thinking_mode=str(
                    getattr(response, "provider_thinking_mode", "") or ""
                ),
                max_retries=int(
                    getattr(response, "provider_sdk_retries", 0) or 0
                ),
                source=str(getattr(response, "provider_source", "") or ""),
                config_fingerprint=fingerprint,
            )
        return resolve_provider_runtime()

    @staticmethod
    def _annotate_provider_failure(
        error: ProviderError,
        *,
        stage: str,
        primary_calls: int,
        structured_calls: int,
    ) -> ProviderError:
        """Attach secret-free failed-call telemetry for outer transaction evidence."""

        error.provider_stage = stage
        error.provider_primary_calls = max(0, int(primary_calls))
        error.structured_output_repair_calls = max(0, int(structured_calls))
        error.provider_call_count = (
            error.provider_primary_calls
            + error.structured_output_repair_calls
        )
        return error

    @staticmethod
    def _merge_usage(*values: dict[str, int]) -> dict[str, int]:
        keys = {key for value in values for key in value}
        return {key: sum(int(value.get(key, 0)) for value in values) for key in keys}


__all__ = [
    "AuthorWriter",
    "PlannerResult",
    "WriterOutputError",
    "WriterProtocol",
    "WriterResult",
]
