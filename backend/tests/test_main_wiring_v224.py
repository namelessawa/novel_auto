"""v2.24 main.py 装配 — access log 过滤 + tasks router 已挂载。"""

from __future__ import annotations

import logging

import pytest


@pytest.fixture
def access_filter():
    # 不直接 import main.py — 它会装配整个 app, 在测试里太重
    # 我们已知 filter 类名, 但走"读取 logger 已绑 filter"的方式验证 main 模块的副作用
    import main  # noqa: F401 — 触发模块级 addFilter 副作用
    access_logger = logging.getLogger("uvicorn.access")
    return [
        f
        for f in access_logger.filters
        if type(f).__name__ == "_AccessLogFilter"
    ]


def _make_record(*, args) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="%s - %s %s",
        args=args,
        exc_info=None,
    )


def test_access_filter_is_attached(access_filter):
    assert len(access_filter) >= 1, "main.py 未给 uvicorn.access 加 access filter"


def test_filter_drops_200(access_filter):
    f = access_filter[0]
    record = _make_record(args=("127.0.0.1:1234", 'GET / HTTP/1.1', 200))
    assert f.filter(record) is False


def test_filter_drops_304(access_filter):
    f = access_filter[0]
    record = _make_record(args=("127.0.0.1:1234", 'GET /static/x.js HTTP/1.1', 304))
    assert f.filter(record) is False


def test_filter_keeps_404(access_filter):
    f = access_filter[0]
    record = _make_record(args=("127.0.0.1:1234", 'GET /missing HTTP/1.1', 404))
    assert f.filter(record) is True


def test_filter_keeps_500(access_filter):
    f = access_filter[0]
    record = _make_record(args=("127.0.0.1:1234", 'POST /api/x HTTP/1.1', 500))
    assert f.filter(record) is True


def test_filter_keeps_when_status_missing(access_filter):
    """args 形状不含 status_code 时, 保留 (宁可多打不漏)。"""
    f = access_filter[0]
    record = _make_record(args=("just-a-string",))
    assert f.filter(record) is True


def test_tasks_router_is_included():
    """main 模块的 FastAPI app 已挂载 /api/tasks 路由。"""
    import main
    paths = [getattr(r, "path", "") for r in main.app.routes]
    assert any(p.startswith("/api/tasks") for p in paths), (
        "未发现 /api/tasks 路由, main.py 可能没 include tasks_router"
    )


# ---- v2.37 — CORS: 通配 origin 禁止与 credentials 并用 ----------------------


def test_cors_policy_wildcard_disables_credentials():
    import main
    origins, allow_credentials = main._cors_policy(["*"])
    assert origins == ["*"]
    assert allow_credentials is False


def test_cors_policy_explicit_origins_keep_credentials():
    import main
    origins, allow_credentials = main._cors_policy(
        ["https://novel.example.com"]
    )
    assert origins == ["https://novel.example.com"]
    assert allow_credentials is True


def test_settings_default_cors_is_not_wildcard():
    """config.json 未配置 cors_origins 时的默认值不得是 ['*']。"""
    from config.settings import _DEFAULT_CORS_ORIGINS
    assert "*" not in _DEFAULT_CORS_ORIGINS
    assert all(o.startswith("http") for o in _DEFAULT_CORS_ORIGINS)
