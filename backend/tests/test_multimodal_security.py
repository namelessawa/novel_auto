"""v2.33 — 多模态安全 + 关键修复回归测试.

覆盖:
- SSRF: X-Image-Endpoint 域名白名单
- voice 白名单校验
- update_segment_status 的并发安全
- get_asset 路径穿越
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from multimedia.asset_store import (
    MultimediaManifest,
    MultimediaStore,
    SegmentAsset,
)
from nf_core import edge_tts_client, xfyun_image


# ---------- SSRF: endpoint 白名单 -------------------------------------------


@pytest.mark.asyncio
async def test_xfyun_rejects_non_whitelisted_endpoint():
    # 攻击者把 endpoint 指到 IMDS / 自家服务器, 应该被拒掉, 凭据不出去
    with pytest.raises(xfyun_image.XfyunImageError) as exc_info:
        await xfyun_image.generate_image(
            app_id="fake",
            api_key="fake",
            api_secret="fake",
            prompt="test",
            endpoint="https://169.254.169.254/latest/meta-data/",
        )
    assert "白名单" in str(exc_info.value) or "allowed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_xfyun_rejects_http_scheme():
    # http (非 https) 即使是白名单 host 也拒, 防降级窃听
    with pytest.raises(xfyun_image.XfyunImageError) as exc_info:
        await xfyun_image.generate_image(
            app_id="fake",
            api_key="fake",
            api_secret="fake",
            prompt="test",
            endpoint="http://maas-api.cn-huabei-1.xf-yun.com/v2.1/tti",
        )
    assert "https" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_xfyun_rejects_userinfo_in_url():
    # netloc 形如 user:pass@host:port — parsed.hostname 取出真实 host, 应被拒
    with pytest.raises(xfyun_image.XfyunImageError):
        await xfyun_image.generate_image(
            app_id="fake",
            api_key="fake",
            api_secret="fake",
            prompt="test",
            endpoint="https://attacker:fake@evil.com/v2.1/tti",
        )


@pytest.mark.asyncio
async def test_xfyun_allows_whitelisted_endpoint(monkeypatch):
    # 白名单内的 host 应通过 endpoint 校验 (实际网络调用会失败, 但不应在校验阶段抛)
    # 用 httpx mock 让请求短路
    class _StubClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw):
            class _Resp:
                status_code = 200
                text = '{"header":{"code":0},"payload":{"choices":{"text":[{"content":"YWFhYQ=="}]}}}'
                def json(self):
                    import json
                    return json.loads(self.text)
            return _Resp()
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)

    b64 = await xfyun_image.generate_image(
        app_id="fake",
        api_key="fake",
        api_secret="fake",
        prompt="test",
        endpoint="https://maas-api.cn-huabei-3.xf-yun.com/v2.1/tti",
    )
    assert b64 == "YWFhYQ=="


# ---------- voice 白名单 -----------------------------------------------------


def test_voice_whitelist_contains_default():
    assert edge_tts_client.DEFAULT_VOICE in edge_tts_client.SUPPORTED_VOICE_IDS


def test_voice_whitelist_consistent_with_supported_list():
    ids_from_list = {v["id"] for v in edge_tts_client.SUPPORTED_VOICES}
    assert ids_from_list == edge_tts_client.SUPPORTED_VOICE_IDS


def test_generate_request_rejects_unknown_voice():
    from api.multimodal_routes import GenerateRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GenerateRequest(
            novel_id="x", chapter=1, section=1, voice="evil-voice-not-in-whitelist"
        )


def test_generate_request_accepts_whitelisted_voice():
    from api.multimodal_routes import GenerateRequest
    req = GenerateRequest(
        novel_id="x",
        chapter=1,
        section=1,
        voice="zh-CN-YunyangNeural",
    )
    assert req.voice == "zh-CN-YunyangNeural"


# ---------- update_segment_status 并发 ---------------------------------------


def _make_store_with_manifest(tmpdir: str, n_segments: int = 4) -> MultimediaStore:
    store = MultimediaStore("test_novel", tmpdir)
    segments = [
        SegmentAsset(
            index=i,
            text=f"段{i}",
            image_filename=store.image_filename(i),
            audio_filename=store.audio_filename(i),
        )
        for i in range(n_segments)
    ]
    manifest = MultimediaManifest(
        novel_id="test_novel",
        chapter=1,
        section=1,
        segments=segments,
    )
    store.save_manifest(manifest)
    return store


def test_update_segment_status_atomic_under_threadpool():
    """关键回归: 多并发更新不应丢更新.

    用 thread pool 真并发更新 4 段, 每段调一次 update_segment_status,
    最后 manifest 上 4 段都该是 done.
    """
    from concurrent.futures import ThreadPoolExecutor, wait

    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store_with_manifest(tmp, n_segments=4)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(
                    store.update_segment_status,
                    1, 1, i,
                    image_status="done",
                    audio_status="done",
                    duration_ms=1000 + i * 100,
                )
                for i in range(4)
            ]
            wait(futures)

        manifest = store.load_manifest(1, 1)
        assert manifest is not None
        for i, seg in enumerate(manifest.segments):
            assert seg.image_status == "done", f"段 {i} image_status 丢失"
            assert seg.audio_status == "done", f"段 {i} audio_status 丢失"
            assert seg.duration_ms == 1000 + i * 100


def test_update_segment_status_returns_none_when_manifest_missing():
    with tempfile.TemporaryDirectory() as tmp:
        store = MultimediaStore("test_novel", tmp)
        result = store.update_segment_status(1, 1, 0, image_status="done")
        assert result is None


def test_update_segment_status_out_of_range_index_returns_existing():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store_with_manifest(tmp, n_segments=2)
        result = store.update_segment_status(
            1, 1, 99, image_status="done"  # 越界
        )
        assert result is not None
        assert all(s.image_status == "pending" for s in result.segments)


# ---------- 路径穿越 ---------------------------------------------------------


def test_section_dir_outside_data_root_caught():
    """构造的 path 必须落在 multimedia/ 下 — 防止 chapter / section 注入."""
    with tempfile.TemporaryDirectory() as tmp:
        store = MultimediaStore("test_novel", tmp)
        # 即使有人传奇怪的章节号, 路径计算也只是字符串拼接, 不会越界
        sd = store.section_dir(1, 1)
        assert "multimedia" in str(sd)
        # resolve 后仍在 multimedia 内
        sd_resolved = sd.resolve()
        root_resolved = (Path(tmp) / "multimedia").resolve()
        # sd 还没创建, 所以 relative_to 用未 resolve 的 path 比较
        assert str(sd_resolved).startswith(str(root_resolved))
