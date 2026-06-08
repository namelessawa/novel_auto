"""v2.33 — 多模态生成: 节文本 → 分段 → 图 + TTS → 视频.

| Method | Path                                                            | 用途                         |
|--------|-----------------------------------------------------------------|------------------------------|
| GET    | /api/multimodal/voices                                          | TTS 音色清单                 |
| POST   | /api/multimodal/segment-preview                                 | 预览分段 (不落盘)            |
| POST   | /api/multimodal/generate                                        | 创建多模态生成任务 (SSE 流)   |
| GET    | /api/multimodal/{novel_id}/{chapter}/{section}/manifest         | 读 manifest                  |
| GET    | /api/multimodal/{novel_id}/list                                 | 列出该 novel 已生成的节       |
| GET    | /api/multimodal/{novel_id}/{chapter}/{section}/asset/{filename} | 下载单个资产 (mp4/png/mp3)    |

任务进度通过通用 /api/tasks/{id}/stream 走, 不重复造 SSE.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

import novel_manager
from auth import User, get_current_user
from multimedia.asset_store import (
    MultimediaManifest,
    MultimediaStore,
    SegmentAsset,
    get_multimedia_store,
)
from nf_core import edge_tts_client, video_composer, xfyun_image
from nf_core.text_segmenter import segment_text
from sections.section_store import get_section_store
from tasks.task_manager import ProgressUpdater, TaskConflict, get_task_manager

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/multimodal", tags=["multimodal"])


# ---------- Schemas ----------------------------------------------------------


class SegmentPreviewRequest(BaseModel):
    novel_id: str
    chapter: int = Field(ge=1)
    section: int = Field(ge=1)


class SegmentPreviewItem(BaseModel):
    index: int
    text: str
    char_count: int


class SegmentPreviewResponse(BaseModel):
    novel_id: str
    chapter: int
    section: int
    source_chars: int
    segments: list[SegmentPreviewItem]


# v2.33 — 讯飞 MaaS 文档支持的 6 档分辨率, 与前端 PRESETS 对齐
SUPPORTED_RESOLUTIONS = {
    (768, 768), (1024, 1024), (1024, 576),
    (1024, 768), (576, 1024), (768, 1024),
}


class GenerateRequest(BaseModel):
    novel_id: str
    chapter: int = Field(ge=1)
    section: int = Field(ge=1)
    voice: str = Field(default=edge_tts_client.DEFAULT_VOICE)
    image_width: int = Field(default=768, ge=128, le=2048)
    image_height: int = Field(default=768, ge=128, le=2048)
    image_prompt_suffix: str = Field(
        default="电影感画面, 写实细节, 高质量插画",
        max_length=256,
        description="拼接到段落原文后面, 引导画风",
    )
    negative_prompt: str = Field(default="低质量, 模糊, 水印, 字幕, 文字", max_length=256)

    @field_validator("voice")
    @classmethod
    def _voice_in_whitelist(cls, v: str) -> str:
        if v not in edge_tts_client.SUPPORTED_VOICE_IDS:
            raise ValueError(
                f"voice {v!r} 不在白名单. 可选: {sorted(edge_tts_client.SUPPORTED_VOICE_IDS)}"
            )
        return v


# ---------- 公开端点 ---------------------------------------------------------


@router.get("/voices")
async def list_voices(current_user: User = Depends(get_current_user)):
    """TTS 音色清单 — 前端 ConfigView 渲染. 不需要 user 凭据."""
    return {"voices": edge_tts_client.SUPPORTED_VOICES, "default": edge_tts_client.DEFAULT_VOICE}


@router.post("/segment-preview", response_model=SegmentPreviewResponse)
async def segment_preview(
    req: SegmentPreviewRequest,
    current_user: User = Depends(get_current_user),
) -> SegmentPreviewResponse:
    """同步切分, 返回分段预览 — 不落盘, 不消耗任何凭据."""
    text = _load_section_text(current_user.id, req.novel_id, req.chapter, req.section)
    segs = segment_text(text)
    return SegmentPreviewResponse(
        novel_id=req.novel_id,
        chapter=req.chapter,
        section=req.section,
        source_chars=sum(1 for c in text if not c.isspace()),
        segments=[
            SegmentPreviewItem(index=s.index, text=s.text, char_count=s.char_count)
            for s in segs
        ],
    )


@router.post("/generate")
async def generate_multimodal(
    req: GenerateRequest,
    current_user: User = Depends(get_current_user),
    x_image_provider: str = Header(default="xfyun", alias="X-Image-Provider"),
    x_image_app_id: str = Header(default="", alias="X-Image-App-Id"),
    x_image_api_key: str = Header(default="", alias="X-Image-Api-Key"),
    x_image_api_secret: str = Header(default="", alias="X-Image-Api-Secret"),
    x_image_model: str = Header(default="", alias="X-Image-Model"),
    x_image_endpoint: str = Header(default="", alias="X-Image-Endpoint"),
):
    """创建多模态生成任务, 返回 task snapshot. 进度通过 /api/tasks/{id}/stream 订阅."""
    if (req.image_width, req.image_height) not in SUPPORTED_RESOLUTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"分辨率 {req.image_width}x{req.image_height} 不支持; 仅 "
                "768x768 / 1024x1024 / 1024x576 / 1024x768 / 576x1024 / 768x1024"
            ),
        )

    provider = (x_image_provider or "xfyun").strip().lower()
    if provider != "xfyun":
        raise HTTPException(
            status_code=501,
            detail=f"多模态当前仅支持 xfyun 图片 (传入 provider={provider!r})",
        )

    # 凭据预校验 — 不让任务跑到一半才发现 401
    missing = []
    if not x_image_app_id.strip():
        missing.append("X-Image-App-Id")
    if not x_image_api_key.strip():
        missing.append("X-Image-Api-Key")
    if not x_image_api_secret.strip():
        missing.append("X-Image-Api-Secret")
    if missing:
        raise HTTPException(status_code=400, detail="讯飞凭据缺失: " + ", ".join(missing))

    # 节存在性检查
    text = _load_section_text(current_user.id, req.novel_id, req.chapter, req.section)
    segs = segment_text(text)
    if not segs:
        raise HTTPException(status_code=400, detail="节文本为空, 无法生成多模态")

    novel = novel_manager.get_novel(current_user.id, req.novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {req.novel_id!r} 不存在")
    novel_title = (novel.get("title") or "").strip()

    # 凭据快照 — 闭包捕获, executor 在后台跑时也能用
    image_creds = {
        "app_id": x_image_app_id.strip(),
        "api_key": x_image_api_key.strip(),
        "api_secret": x_image_api_secret.strip(),
        "domain": (x_image_model or "").strip() or "general",
        "endpoint": (x_image_endpoint or "").strip() or xfyun_image.XFYUN_DEFAULT_ENDPOINT,
    }

    executor = _make_executor(
        chapter=req.chapter,
        section=req.section,
        source_text=text,
        segments=[(s.index, s.text) for s in segs],
        voice=req.voice,
        image_width=req.image_width,
        image_height=req.image_height,
        prompt_suffix=req.image_prompt_suffix,
        negative_prompt=req.negative_prompt,
        image_creds=image_creds,
    )

    mgr = get_task_manager()
    try:
        snap = await mgr.create_task(
            user_id=current_user.id,
            novel_id=req.novel_id,
            novel_title=novel_title,
            kind="multimodal_generation",
            executor=executor,
            target_words=len(segs),  # 复用进度字段表示总段数
            min_words=0,
            max_ticks=0,
            chapter=req.chapter,
            section_no=req.section,
        )
    except TaskConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    novel_manager.touch_last_accessed(current_user.id, req.novel_id)
    return snap.model_dump(mode="json")


@router.get("/{novel_id}/list")
async def list_multimodal_sections(
    novel_id: str,
    current_user: User = Depends(get_current_user),
):
    """列出该 novel 已生成的多模态节 (按 chapter, section 升序)."""
    novel = novel_manager.get_novel(current_user.id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    data_dir = novel_manager.get_novel_data_dir(current_user.id, novel_id)
    store = get_multimedia_store(novel_id, data_dir)
    items = []
    for ch, s in store.list_sections():
        manifest = store.load_manifest(ch, s)
        if manifest is None:
            continue
        items.append({
            "chapter": ch,
            "section": s,
            "segment_count": len(manifest.segments),
            "video_status": manifest.video_status,
            "video_filename": manifest.video_filename,
            "updated_at": manifest.updated_at,
        })
    return {"novel_id": novel_id, "items": items}


@router.get("/{novel_id}/{chapter}/{section}/manifest")
async def get_manifest(
    novel_id: str,
    chapter: int,
    section: int,
    current_user: User = Depends(get_current_user),
):
    novel = novel_manager.get_novel(current_user.id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    data_dir = novel_manager.get_novel_data_dir(current_user.id, novel_id)
    store = get_multimedia_store(novel_id, data_dir)
    manifest = store.load_manifest(chapter, section)
    if manifest is None:
        raise HTTPException(status_code=404, detail="manifest 不存在 — 该节未生成多模态资产")
    return manifest.model_dump(mode="json")


@router.get("/{novel_id}/{chapter}/{section}/asset/{filename}")
async def get_asset(
    novel_id: str,
    chapter: int,
    section: int,
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """下载资产 — 图片 / 音频 / 视频 / 字幕都走这个端点."""
    # 第一道防御 — 拒绝任何分隔符 / 父引用. URL 已经被 FastAPI 解码, 这里看到的
    # 就是真实字符. relative_to 才是最终防线 (见下), 这里属于 defense-in-depth.
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    # 用 Path.suffix 精确判断, 而不是 endswith — 后者会被 foo.png.evil 之类
    # 多扩展名绕过 (实际 suffix 是 .evil).
    allowed_suffixes = {".png", ".mp3", ".mp4", ".srt", ".json"}
    if Path(filename).suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="不允许的文件类型")

    novel = novel_manager.get_novel(current_user.id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    data_dir = novel_manager.get_novel_data_dir(current_user.id, novel_id)
    store = get_multimedia_store(novel_id, data_dir)

    path = store.section_dir(chapter, section) / filename
    # 再次校验路径在 section_dir 之内
    try:
        path.resolve().relative_to(store.section_dir(chapter, section).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="路径越界")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")

    media_type = {
        ".png": "image/png",
        ".mp3": "audio/mpeg",
        ".mp4": "video/mp4",
        ".srt": "application/x-subrip",
        ".json": "application/json",
    }.get(Path(filename).suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=filename)


# ---------- 内部 -------------------------------------------------------------


def _load_section_text(user_id: str, novel_id: str, chapter: int, section: int) -> str:
    """从 SectionStore 读指定节的 content. 不存在 → 404."""
    novel = novel_manager.get_novel(user_id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
    store = get_section_store(novel_id, data_dir=data_dir)
    for sec in store.list_all():
        if sec.chapter == chapter and sec.section == section:
            return sec.content
    raise HTTPException(
        status_code=404,
        detail=f"节 ({chapter}, {section}) 不存在 — 请先在控制台生成该节文本",
    )


def _make_executor(
    *,
    chapter: int,
    section: int,
    source_text: str,
    segments: list[tuple[int, str]],
    voice: str,
    image_width: int,
    image_height: int,
    prompt_suffix: str,
    negative_prompt: str,
    image_creds: dict[str, str],
) -> Callable[[ProgressUpdater, str, str], Awaitable[dict]]:
    """构造 task_manager 的 executor 闭包.

    image_creds 在 _executor 结束 (无论成功/失败) 时会被清零, 避免长尾内存里
    持留讯飞 APISecret. task_manager 不会强制 GC 已完成任务, 凭据可能驻留小时级.
    """

    async def _executor(updater: ProgressUpdater, user_id: str, novel_id: str) -> dict:
        try:
            return await _run_executor(
                updater=updater,
                user_id=user_id,
                novel_id=novel_id,
                chapter=chapter,
                section=section,
                source_text=source_text,
                segments=segments,
                voice=voice,
                image_width=image_width,
                image_height=image_height,
                prompt_suffix=prompt_suffix,
                negative_prompt=negative_prompt,
                image_creds=image_creds,
            )
        finally:
            # 凭据零化 — 长生命周期闭包不应继续持有 APISecret
            for k in list(image_creds.keys()):
                image_creds[k] = ""

    return _executor


async def _run_executor(
    *,
    updater: ProgressUpdater,
    user_id: str,
    novel_id: str,
    chapter: int,
    section: int,
    source_text: str,
    segments: list[tuple[int, str]],
    voice: str,
    image_width: int,
    image_height: int,
    prompt_suffix: str,
    negative_prompt: str,
    image_creds: dict[str, str],
) -> dict:
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
    store = get_multimedia_store(novel_id, data_dir)

    # 初始 manifest — 全部 pending
    seg_assets = [
        SegmentAsset(
            index=idx,
            text=text,
            char_count=sum(1 for c in text if not c.isspace()),
            image_filename=store.image_filename(idx),
            audio_filename=store.audio_filename(idx),
        )
        for idx, text in segments
    ]
    manifest = MultimediaManifest(
        novel_id=novel_id,
        chapter=chapter,
        section=section,
        source_text=source_text,
        voice=voice,
        image_provider="xfyun",
        image_width=image_width,
        image_height=image_height,
        segments=seg_assets,
        video_filename="output.mp4",
        video_status="pending",
    )
    store.save_manifest(manifest)

    total = len(seg_assets)
    updater.set(
        current_words=0,
        tick_count=0,
        last_message=f"开始: 共 {total} 段, 并行生成图片 + TTS",
    )

    # 共享 progress 计数 — 关键: 所有并发 _process_segment 必须看到同一个
    # 状态对象. 之前每个 task 各拿一份导致进度永远 1/N.
    # asyncio.Lock 保护读写 — 严格说 CPython GIL 下 int +=1 是原子的, 但
    # +read+write+读 progress_state 不止 +=1 一行, 显式加锁意图更清楚.
    progress = {"done": 0}
    progress_lock = asyncio.Lock()

    async def _bump_progress() -> None:
        async with progress_lock:
            progress["done"] += 1
            done_now = progress["done"]
        updater.set(
            current_words=done_now,
            last_message=f"段 {done_now}/{total} 完成",
        )

    # 并行: 每段同时跑 image + audio
    tasks = [
        _process_segment(
            store=store,
            asset=asset,
            chapter=chapter,
            section=section,
            image_width=image_width,
            image_height=image_height,
            prompt_suffix=prompt_suffix,
            negative_prompt=negative_prompt,
            image_creds=image_creds,
            voice=voice,
            on_done=_bump_progress,
        )
        for asset in seg_assets
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    fail_count = 0
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            fail_count += 1
            # 内部错误细节走 logger, 不进入返回给前端的 task.error 字段;
            # 用户能在 manifest.segments[i].image_error / audio_error 里看到对应段的错.
            logger.warning("segment %d 失败: %s", i, r)

    # manifest 此时被各 task 通过 update_segment_status 更新过, 重新载入拿到最新
    reloaded = store.load_manifest(chapter, section)
    if reloaded is None:
        raise RuntimeError("manifest 丢失, 无法继续 (磁盘异常?)")
    manifest = reloaded

    if fail_count > 0:
        # 部分段失败 — 不合成视频, 抛错让 task 状态 = failed.
        # 不暴露段细节, 让用户去 manifest 看.
        raise RuntimeError(
            f"{fail_count}/{total} 段生成失败, 详情见 manifest. 修复后可重新生成."
        )

    updater.set(last_message=f"全部 {total} 段就绪, 开始合成视频…")

    # 合成视频 — 走 async 版本, 内部 semaphore 限并发
    work_dir = store.section_dir(chapter, section)
    items = [
        video_composer.VideoSegmentSpec(
            image_filename=a.image_filename,
            audio_filename=a.audio_filename,
            duration_ms=a.duration_ms,
            subtitle_text=a.text,
        )
        for a in manifest.segments
    ]
    manifest = manifest.model_copy(update={"video_status": "running"})
    store.save_manifest(manifest)
    try:
        output = await video_composer.compose_video_async(
            work_dir=str(work_dir),
            items=items,
            output_filename=manifest.video_filename or "output.mp4",
        )
    except Exception as e:
        manifest = manifest.model_copy(
            update={"video_status": "failed", "video_error": str(e)}
        )
        store.save_manifest(manifest)
        raise

    manifest = manifest.model_copy(
        update={
            "video_status": "done",
            "video_error": "",
            "video_filename": output.name,
        }
    )
    store.save_manifest(manifest)

    updater.set(last_message=f"完成: {output.name}")
    return {
        "result_title": f"第{chapter}章 第{section}节 · 多模态",
        "result_word_count": total,
        "chapter": chapter,
        "section_no": section,
    }


async def _process_segment(
    *,
    store: MultimediaStore,
    asset: SegmentAsset,
    chapter: int,
    section: int,
    image_width: int,
    image_height: int,
    prompt_suffix: str,
    negative_prompt: str,
    image_creds: dict[str, str],
    voice: str,
    on_done: Callable[[], Awaitable[None]],
) -> None:
    """处理单段: 并行跑图片 + TTS, 完成后写 manifest + 推进度.

    图片错就标 image_status=failed; 音频错就标 audio_status=failed.
    只有两个都成功才会调 on_done() 推进进度, 否则 raise RuntimeError
    (上层 gather(return_exceptions=True) 捕获并计入 fail_count).
    """
    image_prompt = f"{asset.text}, {prompt_suffix}" if prompt_suffix else asset.text

    async def _gen_image() -> tuple[str, str]:
        try:
            b64 = await xfyun_image.generate_image(
                app_id=image_creds["app_id"],
                api_key=image_creds["api_key"],
                api_secret=image_creds["api_secret"],
                prompt=image_prompt,
                width=image_width,
                height=image_height,
                domain=image_creds["domain"],
                endpoint=image_creds["endpoint"],
                negative_prompt=negative_prompt,
            )
            if not b64:
                raise ValueError("讯飞返回空 base64 图片数据")
            png_bytes = base64.b64decode(b64)
            if not png_bytes:
                raise ValueError("base64 解码出 0 字节, 拒绝写盘")
            store.write_image(chapter, section, asset.index, png_bytes)
            return ("done", "")
        except Exception as e:
            return ("failed", str(e))

    async def _gen_audio() -> tuple[str, str, int]:
        try:
            audio_path = store.audio_path(chapter, section, asset.index)
            duration_ms = await edge_tts_client.synthesize(
                text=asset.text,
                output_path=str(audio_path),
                voice=voice,
            )
            return ("done", "", duration_ms)
        except Exception as e:
            return ("failed", str(e), 0)

    image_result, audio_result = await asyncio.gather(
        _gen_image(), _gen_audio(), return_exceptions=False
    )
    img_status, img_err = image_result
    aud_status, aud_err, dur = audio_result

    # 走 store 的 locked 接口 — 整个 load+modify+save 在锁内, 不会被
    # 其他段的并发更新覆盖
    store.update_segment_status(
        chapter,
        section,
        asset.index,
        image_status=img_status,
        image_error=img_err,
        audio_status=aud_status,
        audio_error=aud_err,
        duration_ms=dur,
    )

    if img_status == "done" and aud_status == "done":
        await on_done()
    else:
        raise RuntimeError(
            f"segment {asset.index} 失败: image={img_status}({img_err or '-'}), "
            f"audio={aud_status}({aud_err or '-'})"
        )
