"""Phase 5-D follow-up #5 (A) — playwright UI verification for ⭐/⚠ rendering.

Skip the OTP flow by:
1. Inserting a test user directly into auth.db
2. Issuing a JWT via the same encode_token function the server uses
3. Loading localhost:3143 with the JWT in localStorage
4. Selecting each of the 3 runbook themes
5. Snapshotting the风格 select dropdown HTML for visual diff

Output: screenshots + assertion summary.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from auth.jwt_utils import encode_token  # noqa: E402
from auth.store import get_user_store  # noqa: E402


_TEST_EMAIL = "ui_verify_dev@example.test"


def setup_test_user() -> tuple[str, str]:
    """Insert test user + return (user_id, jwt_token)."""
    store = get_user_store()
    existing = store.get_by_email(_TEST_EMAIL.lower())
    if existing:
        user_id = existing["id"]
    else:
        user_id = store.create(_TEST_EMAIL.lower())["id"]
    token = encode_token(user_id=user_id, email=_TEST_EMAIL.lower())
    return user_id, token


def main() -> int:
    user_id, token = setup_test_user()
    print(f"test user: id={user_id} email={_TEST_EMAIL}")
    print(f"jwt: {token[:30]}...")

    out_dir = _REPO_ROOT / "docs" / "iter" / "ui-verify-phase5d"
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    findings: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        # 1. Navigate to root to establish localStorage origin
        page.goto("http://127.0.0.1:3143/", timeout=30_000)

        # 2. Set JWT in localStorage where the app expects it
        page.evaluate(
            """(t) => { localStorage.setItem('novel_auto_jwt', t); }""",
            token,
        )

        # 3. Reload to pick up auth from localStorage
        page.goto("http://127.0.0.1:3143/", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=20_000)
        # Give the React app a moment to fetch /api/presets after mount.
        page.wait_for_timeout(2000)

        # Initial screenshot
        page.screenshot(path=str(out_dir / "0-initial.png"), full_page=True)

        # 4. Find theme select. Match by the label that precedes it.
        theme_select_locator = page.locator(
            "select.input-field"
        ).first
        # Snapshot raw HTML
        html_initial = theme_select_locator.evaluate("(el) => el.outerHTML")
        findings.append(
            f"theme select count: {page.locator('select.input-field').count()}"
        )
        if "(自定义 seed)" not in html_initial:
            findings.append(
                f"WARNING: first select missing '(自定义 seed)' default option; "
                f"got: {html_initial[:200]}"
            )

        # 5. Select each runbook theme and snapshot the style select
        for theme_key in ("steampunk_archive", "republic_spy", "apocalypse_wasteland"):
            try:
                theme_select_locator.select_option(value=theme_key)
            except Exception as e:
                findings.append(f"ERROR: cannot select theme {theme_key}: {e}")
                continue

            page.wait_for_timeout(500)
            style_select = page.locator("select.input-field").nth(1)
            style_html = style_select.evaluate("(el) => el.outerHTML")

            page.screenshot(
                path=str(out_dir / f"1-{theme_key}.png"), full_page=True
            )
            (out_dir / f"1-{theme_key}-style-select.html").write_text(
                style_html, encoding="utf-8"
            )

            has_star = "⭐" in style_html
            has_warn = "⚠" in style_html
            has_mean = any(f"({m}" in style_html for m in ("4.", "5.", "3."))
            findings.append(
                f"theme={theme_key}: ⭐={'YES' if has_star else 'NO'} "
                f"⚠={'YES' if has_warn else 'NO'} mean_numbers={'YES' if has_mean else 'NO'}"
            )

            # Also check the hint below the select
            hint_text = page.evaluate(
                """() => {
                    const sels = document.querySelectorAll('select.input-field');
                    if (sels.length < 2) return null;
                    const div = sels[1].parentElement;
                    return div ? div.textContent : null;
                }"""
            )
            if hint_text and "本主题推荐" in hint_text:
                findings.append(
                    f"  hint visible: {hint_text.strip()[:120]}"
                )

        browser.close()

    findings_path = out_dir / "findings.txt"
    findings_path.write_text("\n".join(findings) + "\n", encoding="utf-8")

    # Stdout uses GBK on Windows console — print ASCII-safe versions only
    print()
    print("== Verification findings (ASCII-stripped for stdout; full in findings.txt) ==")
    for f in findings:
        safe = (
            f.replace("⭐", "[STAR]")
            .replace("⚠", "[WARN]")
        )
        print(f"  {safe}")
    print(f"\nScreenshots + HTML in: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
