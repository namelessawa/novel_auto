"""Whole-book production specification, outline, and style profile APIs.

This router intentionally contains only the author-owned CRUD and preview
surface.  Durable production job controls live beside the production runtime
and can mount this router together with their own endpoints.
"""

from __future__ import annotations

import re
from contextlib import ExitStack, contextmanager
from typing import Any, Iterator, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

import novel_manager
from auth import User, get_current_user
from nf_core.llm_client import llm_client
from nf_core.provider_runtime import ProviderError
from story.models import StoryBible
from story.outline_generator import (
    OutlineGenerationError,
    WholeBookOutlineGenerator,
)
from story.persistence import PersistenceError, RevisionConflict, StoryBibleStore
from story.production_models import (
    BookOutline,
    BookOutlineUpdate,
    NovelProductionSpec,
    NovelProductionSpecUpdate,
    ProductionModel,
    StyleProfile,
    StyleProfileCreate,
    StyleProfileUpdate,
    utc_now,
)
from story.production_persistence import (
    ActiveStyleBinding,
    ActiveStyleStore,
    BookOutlineStore,
    ProductionChapterStore,
    ProductionSpecStore,
    StyleProfileStore,
    ensure_production_domain,
)
from story.production_service import production_boundary_lock
from story.style_features import derive_style_anchors


router = APIRouter(prefix="/api/novels/{novel_id}", tags=["author-production"])

_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:api[_ -]?(?:key|secret)\s*[:=]|authorization\s*[:=]|"
    r"bearer\s+\S+|\bsk-[A-Za-z0-9_-]{8,}|"
    r"traceback\s+\(most recent call last\))"
)


class OutlineGenerateRequest(ProductionModel):
    expected_spec_revision: int = Field(ge=1)
    expected_outline_revision: int | None = Field(default=None, ge=1)


class StyleProfileCreateRequest(StyleProfileCreate):
    """Create a style or copy an existing profile under a new user-owned ID."""

    copy_from_profile_id: str | None = Field(default=None, min_length=1)
    source_profile_id: str | None = Field(default=None, min_length=1)


class StyleActivationRequest(ProductionModel):
    expected_revision: int = Field(ge=1)
    expected_spec_revision: int = Field(ge=1)
    applies_from_chapter_ordinal: int | None = Field(default=None, ge=1)


class StylePreviewRequest(ProductionModel):
    expected_revision: int = Field(ge=1)
    sample_goal: str = Field(
        default="Write a short, non-canonical scene demonstrating this style.",
        min_length=1,
        max_length=2_000,
    )


class _Domain:
    def __init__(self, data_dir: str, novel: dict[str, Any]) -> None:
        self.data_dir = data_dir
        self.novel = novel
        self.bible_store = StoryBibleStore(data_dir)
        self.spec_store = ProductionSpecStore(data_dir, self._fallback_spec)
        self.outline_store = BookOutlineStore(data_dir)
        self.chapter_store = ProductionChapterStore(data_dir)
        self.style_store = StyleProfileStore(data_dir)
        self.active_store = ActiveStyleStore(data_dir, self._missing_active_style)

    def _fallback_spec(self) -> NovelProductionSpec:
        bible = self.bible_store.load()
        return NovelProductionSpec(
            title=str(self.novel.get("title") or bible.title or "Untitled novel"),
            premise=(
                bible.premise
                or bible.source_seed
                or "A long-form story awaiting a confirmed premise."
            ),
            genre=bible.genre,
            theme=bible.theme or "Theme awaiting confirmation.",
            central_question=bible.central_question,
            ending_direction=bible.ending_direction,
        )

    @staticmethod
    def _missing_active_style() -> ActiveStyleBinding:
        raise PersistenceError("active_style.json is missing after migration")


def _api_error(
    status: int,
    code: str,
    message: str,
    **details: Any,
) -> NoReturn:
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message, "details": details},
    )


def _owned_domain(user_id: str, novel_id: str) -> tuple[_Domain, Any]:
    try:
        novel = novel_manager.get_novel(user_id, novel_id)
    except ValueError:
        _api_error(404, "NOVEL_NOT_FOUND", "作品不存在")
    if novel is None:
        # A tenant must not be able to distinguish another user's novel from a
        # genuinely missing ID.
        _api_error(404, "NOVEL_NOT_FOUND", "作品不存在")
    try:
        data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
        migration = ensure_production_domain(
            data_dir,
            title=str(novel.get("title") or ""),
        )
        domain = _Domain(data_dir, novel)
        _reconcile_active_style(domain)
        return domain, migration
    except HTTPException:
        raise
    except PersistenceError:
        _api_error(
            500,
            "PRODUCTION_DATA_UNAVAILABLE",
            "作品生产数据暂时无法读取",
        )


@contextmanager
def _locked_stores(*stores: Any) -> Iterator[None]:
    """Acquire document locks in canonical path order to prevent deadlocks."""

    unique = {str(store.path): store for store in stores}
    with ExitStack() as stack:
        for path in sorted(unique):
            stack.enter_context(unique[path].lock)
        yield


def _revision_conflict(exc: RevisionConflict) -> NoReturn:
    _api_error(
        409,
        "REVISION_CONFLICT",
        "数据已被其他会话更新，请重新载入",
        expected=exc.expected,
        actual=exc.actual,
    )


def _reconcile_active_style(domain: _Domain) -> None:
    """Heal the only possible cross-document activation crash window.

    ``active_style.json`` is authoritative and is written first by activation.
    If a process exits before the matching spec write, the next API request
    advances the spec revision once and restores the derived profile ID.
    """

    with _locked_stores(domain.active_store, domain.spec_store):
        binding = domain.active_store.load()
        spec = domain.spec_store.load()
        if spec.active_style_profile_id == binding.style_profile_id:
            return
        domain.spec_store.save(
            spec.model_copy(
                update={
                    "revision": spec.revision + 1,
                    "active_style_profile_id": binding.style_profile_id,
                    "updated_at": utc_now(),
                }
            )
        )


def _public_validation_errors(errors: list[str]) -> list[str]:
    public: list[str] = []
    for value in errors[:80]:
        first_line = str(value or "").splitlines()[0][:300]
        if _SENSITIVE_TEXT.search(first_line):
            first_line = "invalid provider output"
        public.append(first_line)
    return public


def _raise_provider_error(exc: ProviderError) -> NoReturn:
    raise HTTPException(status_code=exc.http_status, detail=exc.to_detail())


def _style_or_404(store: StyleProfileStore, style_id: str) -> StyleProfile:
    try:
        return store.get(style_id)
    except KeyError:
        _api_error(404, "STYLE_PROFILE_NOT_FOUND", "风格档案不存在")


def _create_payload_with_derived_anchors(
    payload: dict[str, Any],
) -> StyleProfileCreate:
    sample = str(payload.get("optional_user_sample") or "")
    anchors = payload.get("derived_style_anchors")
    anchors_present = bool(
        anchors
        and any(str(anchor).strip() for anchor in anchors)
    )
    if sample.strip() and not anchors_present:
        payload = {
            **payload,
            "derived_style_anchors": derive_style_anchors(sample),
        }
    return StyleProfileCreate.model_validate(payload)


def _update_with_derived_anchors(
    request: StyleProfileUpdate,
    current: StyleProfile,
) -> StyleProfileUpdate:
    sample_was_supplied = request.optional_user_sample is not None
    anchors_were_supplied = request.derived_style_anchors is not None
    anchors_present = bool(
        request.derived_style_anchors
        and any(
            str(anchor).strip()
            for anchor in request.derived_style_anchors
        )
    )
    should_derive = (
        sample_was_supplied and not anchors_present
    ) or (
        anchors_were_supplied
        and not anchors_present
        and bool(current.optional_user_sample.strip())
    )
    if not should_derive:
        return request
    effective_sample = (
        request.optional_user_sample
        if request.optional_user_sample is not None
        else current.optional_user_sample
    )
    if not str(effective_sample or "").strip():
        return request
    return request.model_copy(
        update={"derived_style_anchors": derive_style_anchors(effective_sample)}
    )


def _next_ungenerated_chapter(
    outline: BookOutline,
    chapter_store: ProductionChapterStore,
) -> int:
    started = {
        chapter.chapter_id
        for chapter in chapter_store.list_all(committed_only=False)
    }
    ordered = sorted(outline.chapters, key=lambda chapter: chapter.ordinal)
    for chapter in ordered:
        if (
            chapter.id not in started
            and chapter.status != "committed"
            and not chapter.committed_section_ids
        ):
            return chapter.ordinal
    return (ordered[-1].ordinal + 1) if ordered else 1


def _outline_edit_errors(current: BookOutline, candidate: BookOutline) -> list[str]:
    """Protect system-owned progress and all already committed chapter data."""

    errors: list[str] = []
    candidate_by_id = {chapter.id: chapter for chapter in candidate.chapters}
    for before in current.chapters:
        after = candidate_by_id.get(before.id)
        if (
            before.status == "committed"
            or before.committed_section_ids
        ) and (after is None or after != before):
            errors.append(f"committed chapter {before.id!r} cannot be edited")
            continue
        if after is not None and (
            after.status != before.status
            or after.committed_section_ids != before.committed_section_ids
        ):
            errors.append(
                f"chapter {before.id!r} progress fields are system-owned"
            )
    return errors


@router.get("/production-spec")
def get_production_spec(
    novel_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, migration = _owned_domain(current_user.id, novel_id)
    return {
        "production_spec": domain.spec_store.load().model_dump(mode="json"),
        "migration": migration.model_dump(mode="json"),
    }


@router.put("/production-spec")
def put_production_spec(
    novel_id: str,
    request: NovelProductionSpecUpdate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    try:
        with _locked_stores(domain.active_store, domain.spec_store):
            binding = domain.active_store.load()
            # ActiveStyleBinding is authoritative.  The wizard may submit the
            # profile it intends to activate next, but only /activate changes
            # the binding; keeping the current ID here avoids split authority.
            normalized = request.model_copy(
                update={"active_style_profile_id": binding.style_profile_id}
            )
            saved = domain.spec_store.update(normalized)
    except RevisionConflict as exc:
        _revision_conflict(exc)
    except ValueError as exc:
        _api_error(422, "PRODUCTION_SPEC_INVALID", str(exc).splitlines()[0][:300])
    return {"production_spec": saved.model_dump(mode="json")}


@router.get("/outline")
def get_book_outline(
    novel_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, migration = _owned_domain(current_user.id, novel_id)
    return {
        "book_outline": domain.outline_store.load().model_dump(mode="json"),
        "migration": migration.model_dump(mode="json"),
    }


@router.put("/outline")
def put_book_outline(
    novel_id: str,
    request: BookOutlineUpdate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    try:
        with _locked_stores(domain.spec_store, domain.outline_store):
            spec = domain.spec_store.load()
            current = domain.outline_store.load()
            if current.revision != request.expected_revision:
                raise RevisionConflict(request.expected_revision, current.revision)
            payload = current.model_dump(mode="python")
            payload.update(
                request.model_dump(
                    mode="python",
                    exclude={"expected_revision"},
                    exclude_none=True,
                )
            )
            payload.update(
                revision=current.revision + 1,
                progress_revision=current.progress_revision,
                created_at=current.created_at,
                updated_at=utc_now(),
            )
            candidate = BookOutline.model_validate(payload)
            errors = [
                *candidate.validation_errors_for(spec),
                *_outline_edit_errors(current, candidate),
            ]
            if errors:
                _api_error(
                    422,
                    "BOOK_OUTLINE_INVALID",
                    "整书大纲未通过确定性校验",
                    errors=_public_validation_errors(errors),
                )
            saved = domain.outline_store.save(candidate)
    except RevisionConflict as exc:
        _revision_conflict(exc)
    except HTTPException:
        raise
    except ValueError as exc:
        _api_error(
            422,
            "BOOK_OUTLINE_INVALID",
            "整书大纲未通过确定性校验",
            errors=_public_validation_errors([str(exc)]),
        )
    return {"book_outline": saved.model_dump(mode="json")}


@router.post("/outline/generate")
async def generate_book_outline(
    novel_id: str,
    request: OutlineGenerateRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    with _locked_stores(domain.spec_store, domain.outline_store):
        spec = domain.spec_store.load()
        current_outline = domain.outline_store.load()
        if spec.revision != request.expected_spec_revision:
            _revision_conflict(
                RevisionConflict(request.expected_spec_revision, spec.revision)
            )
        if (
            request.expected_outline_revision is not None
            and current_outline.revision != request.expected_outline_revision
        ):
            _revision_conflict(
                RevisionConflict(
                    request.expected_outline_revision,
                    current_outline.revision,
                )
            )
        if any(
            chapter.status == "committed" or chapter.committed_section_ids
            for chapter in current_outline.chapters
        ):
            _api_error(
                409,
                "OUTLINE_HAS_COMMITTED_CHAPTERS",
                "已有提交章节时不能重新生成整书大纲",
            )
        captured_spec_revision = spec.revision
        captured_outline_revision = current_outline.revision
        bible: StoryBible = domain.bible_store.load()

    try:
        result = await WholeBookOutlineGenerator().generate(spec=spec, bible=bible)
    except ProviderError as exc:
        _raise_provider_error(exc)
    except OutlineGenerationError as exc:
        _api_error(
            502,
            exc.code,
            "模型输出未通过整书大纲校验",
            errors=_public_validation_errors(exc.errors),
        )

    try:
        with _locked_stores(domain.spec_store, domain.outline_store):
            latest_spec = domain.spec_store.load()
            latest_outline = domain.outline_store.load()
            if latest_spec.revision != captured_spec_revision:
                raise RevisionConflict(
                    captured_spec_revision,
                    latest_spec.revision,
                )
            if latest_outline.revision != captured_outline_revision:
                raise RevisionConflict(
                    captured_outline_revision,
                    latest_outline.revision,
                )
            candidate = result.proposal.as_book_outline(
                revision=latest_outline.revision + 1,
                progress_revision=latest_outline.progress_revision,
            ).model_copy(
                update={
                    # Provider structure can never manufacture production
                    # progress or formal commits.
                    "chapters": [
                        chapter.model_copy(
                            update={
                                "status": "draft",
                                "committed_section_ids": [],
                            }
                        )
                        for chapter in result.proposal.chapters
                    ],
                    "created_at": latest_outline.created_at,
                    "updated_at": utc_now(),
                }
            )
            errors = candidate.validation_errors_for(latest_spec)
            if errors:
                _api_error(
                    422,
                    "BOOK_OUTLINE_INVALID",
                    "整书大纲未通过最终确定性校验",
                    errors=_public_validation_errors(errors),
                )
            saved = domain.outline_store.save(candidate)
    except RevisionConflict as exc:
        _revision_conflict(exc)
    return {
        "book_outline": saved.model_dump(mode="json"),
        "provider_calls": result.provider_calls,
        "repair_performed": result.repair_performed,
        "usage": result.usage,
    }


@router.get("/style-profiles")
def get_style_profiles(
    novel_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    return {
        "profiles": [
            profile.model_dump(mode="json") for profile in domain.style_store.list()
        ],
        "active_style": domain.active_store.load().model_dump(mode="json"),
    }


@router.post("/style-profiles", status_code=201)
def create_style_profile(
    novel_id: str,
    request: StyleProfileCreateRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    source_id = request.copy_from_profile_id or request.source_profile_id
    if (
        request.copy_from_profile_id
        and request.source_profile_id
        and request.copy_from_profile_id != request.source_profile_id
    ):
        _api_error(
            422,
            "STYLE_PROFILE_INVALID",
            "只能指定一个待复制的风格档案",
        )
    try:
        if source_id:
            source = _style_or_404(domain.style_store, source_id)
            create_fields = set(StyleProfileCreate.model_fields)
            payload = {
                key: value
                for key, value in source.model_dump(mode="python").items()
                if key in create_fields
            }
            payload["name"] = request.name
            profile = domain.style_store.create(
                _create_payload_with_derived_anchors(payload)
            )
        else:
            create_fields = set(StyleProfileCreate.model_fields)
            payload = {
                key: value
                for key, value in request.model_dump(mode="python").items()
                if key in create_fields
            }
            profile = domain.style_store.create(
                _create_payload_with_derived_anchors(payload)
            )
    except KeyError:
        _api_error(404, "STYLE_PROFILE_NOT_FOUND", "待复制的风格档案不存在")
    except ValueError as exc:
        _api_error(422, "STYLE_PROFILE_INVALID", str(exc).splitlines()[0][:300])
    return {"style_profile": profile.model_dump(mode="json")}


@router.put("/style-profiles/{style_id}")
def put_style_profile(
    novel_id: str,
    style_id: str,
    request: StyleProfileUpdate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    try:
        current = _style_or_404(domain.style_store, style_id)
        profile = domain.style_store.update(
            style_id,
            _update_with_derived_anchors(request, current),
        )
    except KeyError:
        _api_error(404, "STYLE_PROFILE_NOT_FOUND", "风格档案不存在")
    except PermissionError:
        _api_error(403, "STYLE_PROFILE_READ_ONLY", "内置风格为只读档案")
    except RevisionConflict as exc:
        _revision_conflict(exc)
    except ValueError as exc:
        _api_error(422, "STYLE_PROFILE_INVALID", str(exc).splitlines()[0][:300])
    return {"style_profile": profile.model_dump(mode="json")}


@router.delete("/style-profiles/{style_id}")
def delete_style_profile(
    novel_id: str,
    style_id: str,
    expected_revision: int = Query(ge=1),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    with _locked_stores(domain.active_store, domain.style_store):
        if domain.active_store.load().style_profile_id == style_id:
            _api_error(
                409,
                "STYLE_PROFILE_ACTIVE",
                "当前启用的风格档案不能删除",
            )
        try:
            domain.style_store.delete(
                style_id,
                expected_revision=expected_revision,
            )
        except KeyError:
            _api_error(404, "STYLE_PROFILE_NOT_FOUND", "风格档案不存在")
        except PermissionError:
            _api_error(403, "STYLE_PROFILE_READ_ONLY", "内置风格为只读档案")
        except RevisionConflict as exc:
            _revision_conflict(exc)
    return {"deleted": True, "style_profile_id": style_id}


@router.post("/style-profiles/{style_id}/activate")
def activate_style_profile(
    novel_id: str,
    style_id: str,
    request: StyleActivationRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    try:
        with production_boundary_lock(domain.data_dir):
            with _locked_stores(
                domain.active_store,
                domain.outline_store,
                domain.spec_store,
                domain.style_store,
            ):
                active = domain.active_store.load()
                spec = domain.spec_store.load()
                outline = domain.outline_store.load()
                profile = _style_or_404(domain.style_store, style_id)
                if active.revision != request.expected_revision:
                    raise RevisionConflict(request.expected_revision, active.revision)
                if spec.revision != request.expected_spec_revision:
                    raise RevisionConflict(request.expected_spec_revision, spec.revision)
                next_ordinal = _next_ungenerated_chapter(
                    outline,
                    domain.chapter_store,
                )
                applies_from = (
                    request.applies_from_chapter_ordinal
                    if request.applies_from_chapter_ordinal is not None
                    else next_ordinal
                )
                if applies_from < next_ordinal:
                    _api_error(
                        422,
                        "STYLE_ACTIVATION_INVALID",
                        "风格只能从下一未开始章节生效",
                        next_ungenerated_chapter_ordinal=next_ordinal,
                    )

                # The binding is the authority and therefore commits first.  A
                # crash between these writes is repaired by
                # _reconcile_active_style.
                binding = domain.active_store.activate(
                    profile,
                    applies_from_chapter_ordinal=applies_from,
                    expected_revision=active.revision,
                )
                saved_spec = domain.spec_store.update(
                    NovelProductionSpecUpdate(
                        expected_revision=spec.revision,
                        active_style_profile_id=profile.id,
                    )
                )
    except RevisionConflict as exc:
        _revision_conflict(exc)
    except HTTPException:
        raise
    except ValueError as exc:
        _api_error(422, "STYLE_ACTIVATION_INVALID", str(exc).splitlines()[0][:300])
    return {
        "active_style": binding.model_dump(mode="json"),
        "production_spec": saved_spec.model_dump(mode="json"),
    }


@router.post("/style-profiles/{style_id}/preview")
async def preview_style_profile(
    novel_id: str,
    style_id: str,
    request: StylePreviewRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    domain, _ = _owned_domain(current_user.id, novel_id)
    profile = _style_or_404(domain.style_store, style_id)
    if profile.revision != request.expected_revision:
        _revision_conflict(
            RevisionConflict(request.expected_revision, profile.revision)
        )

    # Deliberately pass only the expression-safe prompt contract.  In
    # particular optional_user_sample and the complete StyleProfile never enter
    # Provider context.
    try:
        response = await llm_client.chat(
            system_prompt=(
                "Write a short Chinese fiction style preview. This is "
                "non-canonical and must not assert or mutate story facts. "
                "Return prose only, without analysis or Markdown."
            ),
            user_prompt=profile.prompt_text()
            + "\nPreview goal: "
            + request.sample_goal,
            temperature=0.4,
            max_tokens=1_200,
            agent_id="style_preview",
            priority="medium",
        )
    except ProviderError as exc:
        _raise_provider_error(exc)

    text = str(response.content or "").strip()
    if not text or _SENSITIVE_TEXT.search(text):
        _api_error(
            502,
            "PROVIDER_OUTPUT_INVALID",
            "模型未返回可安全展示的风格预览",
        )
    return {
        "preview": {
            "text": text,
            "style_profile_id": profile.id,
            "style_revision": profile.revision,
            "prompt_hash": profile.prompt_hash,
        },
        "usage": {
            "prompt_tokens": int(response.usage_prompt_tokens or 0),
            "completion_tokens": int(response.usage_completion_tokens or 0),
            "total_tokens": int(response.usage_prompt_tokens or 0)
            + int(response.usage_completion_tokens or 0),
        },
    }


__all__ = ["router"]
