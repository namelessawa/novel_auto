"""Fail-closed acceptance orchestrator for the final long-novel cycle.

Each invocation advances exactly one phase.  Real-provider phases are possible
only after a green offline receipt for the identical branch, HEAD, source-tree
hash, protected user files, and immutable previous-evidence tree.  No phase is
resumable or reusable: interrupted or failed work requires a new evidence root.

This runner never receives a credential on the command line.  The sole secret
source is the explicit read-only ``--provider-file``.  Subprocess output is
redacted in memory before any log is written, while real-provider logs persist
metadata only (never raw responses or prose).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
CYCLE_ID = "p6-provider-init-final-20260730"
BASELINE_HEAD = "834120c860fe05f796ccfa3f65c0b981e777df9a"
EXPECTED_BRANCH = "codex/final-long-novel-custom-style-20260730"
EXPECTED_PROVIDER = "custom"
EXPECTED_MODEL = "glm-5.2"
EXPECTED_THINKING_MODE = "disabled"
EXPECTED_SDK_RETRIES = 0
PHASES = ("offline", "probe", "g1", "g2", "product", "final")
HISTORICAL_STYLES = (
    "literary",
    "noir_cold",
    "warm_healing",
    "hot_blooded",
    "classical_chapter",
)
FINAL_FILENAMES = (
    "report.json",
    "report.md",
    "manifest.json",
    "artifact-sha256.json",
    "recovery.md",
)
OFFLINE_CHECK_NAMES = (
    "pytest_backend",
    "ruff",
    "compileall",
    "frontend_author_tests",
    "frontend_build",
    "frontend_audit",
    "git_diff_check",
    "recorded_author_smoke",
    "recorded_long_30x2_smoke",
    "exact_secret_scan",
    "generic_secret_scan",
    "untracked_sensitive_files",
)


class AcceptanceError(RuntimeError):
    """A hard precondition, integrity check, or acceptance gate failed."""


class SecretLeakError(AcceptanceError):
    """A new source or staged artifact contains credential material."""


@dataclass(frozen=True)
class CommandExecution:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


CommandRunner = Callable[[Sequence[str], Path], CommandExecution]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_text(path: Path, value: str) -> None:
    _atomic_write(path, value.encode("utf-8"))


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcceptanceError(f"expected JSON object: {path.name}")
    return value


def _tree_hash(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise AcceptanceError(f"protected tree is missing: {root}")
    digest = hashlib.sha256()
    count = 0
    total_bytes = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            relative = path.relative_to(root).as_posix()
            payload = os.readlink(path).encode("utf-8", errors="surrogatepass")
        elif path.is_file():
            relative = path.relative_to(root).as_posix()
            payload = path.read_bytes()
        else:
            continue
        count += 1
        total_bytes += len(payload)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return {
        "sha256": digest.hexdigest().upper(),
        "file_count": count,
        "bytes": total_bytes,
    }


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise AcceptanceError("git inspection failed")
    return result.stdout.strip()


def _repo_identity(*, evidence_root: Path | None = None) -> dict[str, str]:
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    merge_base = _git("merge-base", BASELINE_HEAD, head)
    if branch != EXPECTED_BRANCH:
        raise AcceptanceError("acceptance branch does not match the frozen contract")
    if merge_base != BASELINE_HEAD:
        raise AcceptanceError("frozen baseline is not an ancestor of evaluated HEAD")
    return {
        "branch": branch,
        "head": head,
        "baseline_head": BASELINE_HEAD,
        "source_tree_sha256": _source_tree_hash(evidence_root=evidence_root),
    }


def _source_paths(*, evidence_root: Path | None = None) -> list[Path]:
    raw_names = _git(
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ).split("\0")
    excluded = evidence_root.resolve() if evidence_root is not None else None
    paths: list[Path] = []
    for name in sorted(item for item in raw_names if item):
        path = (ROOT / name).resolve()
        if excluded is not None and (path == excluded or path.is_relative_to(excluded)):
            continue
        if path.is_file():
            paths.append(path)
    return paths


def _source_tree_hash(*, evidence_root: Path | None = None) -> str:
    digest = hashlib.sha256()
    known = {path.resolve(): path for path in _source_paths(evidence_root=evidence_root)}
    tracked_names = _git("ls-files", "--cached", "-z").split("\0")
    for name in sorted(item for item in tracked_names if item):
        path = (ROOT / name).resolve()
        if evidence_root is not None and (
            path == evidence_root.resolve()
            or path.is_relative_to(evidence_root.resolve())
        ):
            continue
        relative = Path(name).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path in known or path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"[DELETED]")
        digest.update(b"\0")
    tracked_resolved = {(ROOT / name).resolve() for name in tracked_names if name}
    for path in sorted(
        (item for item in known if item not in tracked_resolved),
        key=lambda item: item.as_posix(),
    ):
        digest.update(path.relative_to(ROOT.resolve()).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest().upper()


def _protected_snapshot(user_root: Path, previous_evidence_root: Path) -> dict[str, Any]:
    user_root = user_root.resolve()
    protected_files: dict[str, Any] = {}
    for name in ("coding.txt", ".env", "config.json"):
        path = user_root / name
        if not path.is_file():
            raise AcceptanceError(f"required protected file is missing: {name}")
        protected_files[name] = {
            "sha256": _sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return {
        "files": protected_files,
        "previous_evidence_tree": _tree_hash(previous_evidence_root),
    }


def _verify_protected(
    expected: dict[str, Any],
    *,
    user_root: Path,
    previous_evidence_root: Path,
) -> None:
    if _protected_snapshot(user_root, previous_evidence_root) != expected:
        raise AcceptanceError("protected files or previous evidence tree drifted")


def _load_provider(provider_file: Path) -> Any:
    backend = str(ROOT / "backend")
    root = str(ROOT)
    for entry in (root, backend):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    from nf_core.provider_runtime import ProviderRuntimeConfig

    config = ProviderRuntimeConfig.from_provider_file(provider_file.resolve())
    mismatches = []
    if config.provider != EXPECTED_PROVIDER:
        mismatches.append("provider")
    if config.model != EXPECTED_MODEL:
        mismatches.append("model")
    if config.thinking_mode != EXPECTED_THINKING_MODE:
        mismatches.append("thinking_mode")
    if config.max_retries != EXPECTED_SDK_RETRIES:
        mismatches.append("sdk_retries")
    if config.source != "provider_file":
        mismatches.append("source")
    if mismatches:
        raise AcceptanceError(
            "provider file violates runtime contract: " + ", ".join(mismatches)
        )
    return config


def _safe_provider(config: Any) -> dict[str, Any]:
    diagnostics = config.diagnostics()
    # key_fingerprint is salted per process; the protected coding.txt SHA binds
    # credential bytes across phases without persisting a volatile identifier.
    keys = (
        "provider",
        "model",
        "source",
        "thinking_mode",
        "retries",
        "credential_present",
        "config_fingerprint",
    )
    return {key: diagnostics[key] for key in keys if key in diagnostics}


def _assert_provider_binding(
    *,
    provider_file: Path,
    user_root: Path,
    config: Any | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    expected_path = (user_root / "coding.txt").resolve()
    if provider_file.resolve() != expected_path:
        raise AcceptanceError("--provider-file must be the user-root coding.txt")
    if config is not None and state is not None:
        if _safe_provider(config) != state.get("provider_runtime"):
            raise AcceptanceError("provider runtime changed after cycle initialization")


class ExactRedactor:
    def __init__(self, *, api_key: str, base_url: str) -> None:
        self._values = {
            "provider_key": api_key,
            "provider_base_url": base_url,
        }

    @property
    def exact_values(self) -> dict[str, str]:
        return dict(self._values)

    def redact(self, value: str) -> tuple[str, dict[str, int]]:
        redacted = value
        counts: dict[str, int] = {}
        for label, secret in self._values.items():
            count = redacted.count(secret) if secret else 0
            if count:
                redacted = redacted.replace(secret, f"[REDACTED_{label.upper()}]")
            counts[label] = count
        return redacted, counts


_GENERIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_style_key", re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])")),
    ("google_api_key", re.compile(r"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{30,}")),
    ("slack_token", re.compile(r"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)


def _placeholder_token(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "test",
            "fake",
            "dummy",
            "example",
            "placeholder",
            "not-render",
            "offline",
            "your-",
            "put-",
            "replace-",
            "changeme",
        )
    )


def scan_exact_secrets(
    paths: Iterable[Path],
    *,
    exact_values: dict[str, str],
    display_root: Path = ROOT,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    scanned = 0
    for path in sorted({item.resolve() for item in paths}, key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        scanned += 1
        raw = path.read_bytes()
        try:
            shown = path.relative_to(display_root.resolve()).as_posix()
        except ValueError:
            shown = path.name
        for label, secret in exact_values.items():
            if secret and secret.encode("utf-8") in raw:
                findings.append({"path": shown, "kind": f"exact_{label}"})
    return {
        "status": "passed" if not findings else "failed",
        "files_scanned": scanned,
        "finding_count": len(findings),
        "findings": findings,
        "secret_values_persisted": False,
    }


def scan_generic_secrets(
    paths: Iterable[Path],
    *,
    display_root: Path = ROOT,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    scanned = 0
    for path in sorted({item.resolve() for item in paths}, key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        scanned += 1
        text = path.read_bytes().decode("utf-8", errors="ignore")
        try:
            shown = path.relative_to(display_root.resolve()).as_posix()
        except ValueError:
            shown = path.name
        for label, pattern in _GENERIC_PATTERNS:
            matches = [item.group(0) for item in pattern.finditer(text)]
            actionable = [item for item in matches if not _placeholder_token(item)]
            if actionable:
                findings.append({"path": shown, "kind": label})
    return {
        "status": "passed" if not findings else "failed",
        "files_scanned": scanned,
        "finding_count": len(findings),
        "findings": findings,
        "secret_values_persisted": False,
    }


def _generic_secret_kinds(value: str) -> list[str]:
    return sorted(
        {
            label
            for label, pattern in _GENERIC_PATTERNS
            for match in pattern.finditer(value)
            if not _placeholder_token(match.group(0))
        }
    )


def _artifact_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def _unsafe_metadata_string(value: str) -> bool:
    stripped = value.strip()
    lowered = stripped.lower()
    if not stripped:
        return False
    if re.fullmatch(r"\[PROTECTED_[A-Z_]+\]", stripped):
        return False
    if (
        "\n" in value
        or "\r" in value
        or "://" in value
        or lowered.startswith(("bearer ", "basic "))
        or stripped.startswith(("{", "["))
        or re.search(r"[\u3400-\u9fff]", stripped)
    ):
        return True
    if ("/" in stripped or "\\" in stripped) and len(stripped) <= 512:
        return False
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", stripped)
    return len(words) >= 4 and bool(re.search(r"[.!?](?:\s|$)", stripped))


def _metadata_only_json(value: Any, *, location: str = "root") -> None:
    forbidden = {
        "api_key",
        "authorization",
        "base_url",
        "body",
        "candidate",
        "choices",
        "completion",
        "content",
        "error",
        "endpoint",
        "headers",
        "message",
        "narrative",
        "narrative_text",
        "optional_user_sample",
        "prose",
        "prompt",
        "raw_output",
        "raw_response",
        "request_body",
        "request_headers",
        "response",
        "response_body",
        "response_headers",
        "sample",
        "system",
        "system_prompt",
        "text",
        "user",
        "user_prompt",
        "url",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                raise AcceptanceError(
                    f"evidence contains forbidden field at {location}.{key}"
                )
            _metadata_only_json(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _metadata_only_json(child, location=f"{location}[{index}]")
    elif isinstance(value, str) and _unsafe_metadata_string(value):
        raise AcceptanceError(f"evidence contains prose or raw payload at {location}")


def _untracked_sensitive_files(*, user_root: Path) -> dict[str, Any]:
    names = _git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    ignored_sensitive = _git(
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        "--",
        ":(glob)**/.env",
        ":(glob)**/coding.txt",
        ":(glob)**/config.json",
        ":(glob)**/*.pem",
        ":(glob)**/*.p12",
        ":(glob)**/*.pfx",
        ":(glob)**/*.key",
    ).split("\0")
    findings: list[str] = []
    sensitive_names = {"coding.txt", ".env", "config.json"}
    protected_paths = {(user_root / name).resolve() for name in sensitive_names}
    for name in sorted({item for item in [*names, *ignored_sensitive] if item}):
        path = Path(name)
        lowered = path.name.lower()
        if (ROOT / path).resolve() in protected_paths:
            continue
        if (
            lowered in sensitive_names
            or lowered.endswith((".pem", ".p12", ".pfx"))
            or (lowered.endswith(".key") and "monkey" not in lowered)
        ):
            findings.append(path.as_posix())
    for name in sensitive_names:
        workspace_path = (ROOT / name).resolve()
        protected_path = (user_root / name).resolve()
        if workspace_path.is_file() and workspace_path != protected_path:
            findings.append(name)
    findings = sorted(set(findings))
    return {
        "status": "passed" if not findings else "failed",
        "finding_count": len(findings),
        "findings": findings,
    }


def _default_command_runner(command: Sequence[str], cwd: Path) -> CommandExecution:
    started = time.perf_counter()
    result = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return CommandExecution(
        command=tuple(str(item) for item in command),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_seconds=round(time.perf_counter() - started, 3),
    )


def _safe_command(command: Sequence[str]) -> list[str]:
    placeholders = {
        "--provider-file": "[PROTECTED_PROVIDER_FILE]",
        "--user-root": "[PROTECTED_USER_ROOT]",
        "--previous-evidence-root": "[PROTECTED_PREVIOUS_EVIDENCE_ROOT]",
        "--evidence-root": "[PROTECTED_EVIDENCE_ROOT]",
        "--output-dir": "[PROTECTED_OUTPUT_DIR]",
        "--data-dir": "[PROTECTED_DATA_DIR]",
    }
    rendered = [str(item) for item in command]
    safe: list[str] = []
    redact_next = ""
    for item in rendered:
        if redact_next:
            safe.append(redact_next)
            redact_next = ""
            continue
        inline_flag = next(
            (flag for flag in placeholders if item.startswith(f"{flag}=")),
            "",
        )
        if inline_flag:
            safe.append(f"{inline_flag}={placeholders[inline_flag]}")
            continue
        safe.append(item)
        redact_next = placeholders.get(item, "")
    return safe


def _record_execution(
    execution: CommandExecution,
    *,
    log_path: Path,
    redactor: ExactRedactor,
    metadata_only: bool,
) -> dict[str, Any]:
    redacted_stdout, stdout_counts = redactor.redact(execution.stdout)
    redacted_stderr, stderr_counts = redactor.redact(execution.stderr)
    redaction_counts = {
        key: stdout_counts.get(key, 0) + stderr_counts.get(key, 0)
        for key in redactor.exact_values
    }
    generic_secret_kinds = _generic_secret_kinds(
        "\n".join((execution.stdout, execution.stderr))
    )
    if metadata_only:
        log_value: Any = {
            "command": _safe_command(execution.command),
            "returncode": execution.returncode,
            "duration_seconds": execution.duration_seconds,
            "redacted_stdout_sha256": _sha256_bytes(redacted_stdout.encode("utf-8")),
            "redacted_stderr_sha256": _sha256_bytes(redacted_stderr.encode("utf-8")),
            "exact_redactions": redaction_counts,
            "raw_output_persisted": False,
        }
        _atomic_json(log_path, log_value)
    else:
        rendered = "\n".join(
            (
                "COMMAND " + json.dumps(_safe_command(execution.command), ensure_ascii=False),
                f"RETURNCODE {execution.returncode}",
                f"DURATION_SECONDS {execution.duration_seconds}",
                "STDOUT",
                redacted_stdout,
                "STDERR",
                redacted_stderr,
            )
        )
        _atomic_text(log_path, rendered)
    if any(redaction_counts.values()) or generic_secret_kinds:
        raise SecretLeakError("subprocess output contained credential material")
    return {
        "status": "passed" if execution.returncode == 0 else "failed",
        "returncode": execution.returncode,
        "duration_seconds": execution.duration_seconds,
        "command": _safe_command(execution.command),
        "log": log_path.name,
        "log_sha256": _sha256_file(log_path),
        "exact_redactions": redaction_counts,
        "generic_secret_kinds": generic_secret_kinds,
        "raw_output_persisted": not metadata_only,
    }


def _offline_external_commands(work_root: Path) -> list[tuple[str, list[str]]]:
    npm = shutil.which("npm") or "npm"
    return [
        (
            "pytest_backend",
            [sys.executable, "-m", "pytest", "backend/tests/", "-q", "-W", "error"],
        ),
        (
            "ruff",
            [sys.executable, "-m", "ruff", "check", "backend", "scripts", "core"],
        ),
        (
            "compileall",
            [sys.executable, "-m", "compileall", "-q", "backend", "scripts", "core"],
        ),
        ("frontend_author_tests", [npm, "--prefix", "frontend", "run", "test:author"]),
        ("frontend_build", [npm, "--prefix", "frontend", "run", "build"]),
        ("frontend_audit", [npm, "--prefix", "frontend", "audit", "--omit=dev"]),
        ("git_diff_check", ["git", "diff", "--check"]),
        (
            "recorded_author_smoke",
            [
                sys.executable,
                "scripts/smoke_author_mode_recorded.py",
                "--data-dir",
                str(work_root / "recorded-author-state"),
            ],
        ),
        (
            "recorded_long_30x2_smoke",
            [
                sys.executable,
                "scripts/smoke_long_novel_recorded.py",
                "--output-dir",
                str(work_root / "recorded-long-output"),
                "--chapters",
                "30",
                "--sections-per-chapter",
                "2",
            ],
        ),
    ]


def _new_state(
    *,
    identity: dict[str, str],
    protected: dict[str, Any],
    provider: dict[str, Any],
    user_root: Path,
    previous_evidence_root: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "final-long-novel-cycle-v1",
        "cycle_id": CYCLE_ID,
        "created_at": _now(),
        "baseline_head": BASELINE_HEAD,
        "expected_branch": EXPECTED_BRANCH,
        "git": identity,
        "authorized_source_tree_sha256": "",
        "authorized_head": "",
        "protected": protected,
        "path_fingerprints": {
            "user_root": _sha256_bytes(str(user_root.resolve()).encode("utf-8")),
            "previous_evidence_root": _sha256_bytes(
                str(previous_evidence_root.resolve()).encode("utf-8")
            ),
        },
        "provider_runtime": provider,
        "phases": {
            phase: {"status": "not_started"} for phase in PHASES
        },
        "secret_values_persisted": False,
    }


def _state_path(evidence_root: Path) -> Path:
    return evidence_root / "cycle-state.json"


def _save_state(evidence_root: Path, state: dict[str, Any]) -> None:
    _metadata_only_json(state)
    _atomic_json(_state_path(evidence_root), state)


def _initialize_cycle(
    *,
    evidence_root: Path,
    user_root: Path,
    previous_evidence_root: Path,
    provider_file: Path,
    config: Any,
) -> dict[str, Any]:
    if evidence_root.exists():
        raise AcceptanceError("evidence root already exists; reuse is forbidden")
    _assert_provider_binding(provider_file=provider_file, user_root=user_root)
    for protected_root in (user_root.resolve(), previous_evidence_root.resolve()):
        if evidence_root.resolve() == protected_root or evidence_root.resolve().is_relative_to(
            protected_root
        ):
            raise AcceptanceError("evidence root cannot be inside a protected tree")
    identity = _repo_identity(evidence_root=evidence_root)
    protected = _protected_snapshot(user_root, previous_evidence_root)
    state = _new_state(
        identity=identity,
        protected=protected,
        provider=_safe_provider(config),
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )
    evidence_root.parent.mkdir(parents=True, exist_ok=True)
    staging = evidence_root.parent / f".{evidence_root.name}.init-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        _save_state(staging, state)
        os.rename(staging, evidence_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return state


def _load_cycle(
    *,
    evidence_root: Path,
    user_root: Path,
    previous_evidence_root: Path,
) -> dict[str, Any]:
    if not evidence_root.is_dir() or not _state_path(evidence_root).is_file():
        raise AcceptanceError("exclusive evidence root is not initialized")
    state = _read_json(_state_path(evidence_root))
    if state.get("cycle_id") != CYCLE_ID:
        raise AcceptanceError("evidence root belongs to another acceptance cycle")
    expected_fingerprints = state.get("path_fingerprints", {})
    actual_fingerprints = {
        "user_root": _sha256_bytes(str(user_root.resolve()).encode("utf-8")),
        "previous_evidence_root": _sha256_bytes(
            str(previous_evidence_root.resolve()).encode("utf-8")
        ),
    }
    if expected_fingerprints != actual_fingerprints:
        raise AcceptanceError("protected root arguments changed between phases")
    _verify_protected(
        state["protected"],
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )
    _verify_completed_artifacts(state, evidence_root=evidence_root)
    return state


def _require_phase(state: dict[str, Any], phase: str) -> None:
    if phase not in PHASES:
        raise AcceptanceError(f"unsupported phase: {phase}")
    if state["phases"][phase]["status"] != "not_started":
        raise AcceptanceError(f"phase {phase} cannot be reused")
    index = PHASES.index(phase)
    incomplete = [
        name
        for name in PHASES[:index]
        if state["phases"][name]["status"] != "passed"
    ]
    if incomplete:
        raise AcceptanceError(
            f"phase {phase} is blocked by: {', '.join(incomplete)}"
        )


def _verify_authorized_source(
    state: dict[str, Any],
    *,
    evidence_root: Path,
) -> dict[str, str]:
    identity = _repo_identity(evidence_root=evidence_root)
    if not state.get("authorized_source_tree_sha256"):
        raise AcceptanceError("current source has no green offline receipt")
    if identity["source_tree_sha256"] != state["authorized_source_tree_sha256"]:
        raise AcceptanceError("source changed after offline; run a new full cycle")
    if identity["head"] != state["authorized_head"]:
        raise AcceptanceError("HEAD changed after offline; run a new full cycle")
    return identity


def _stage_dir(evidence_root: Path, phase: str) -> Path:
    target = evidence_root / phase
    claim = evidence_root / f".{phase}.claim"
    abandoned = list(evidence_root.glob(f".{phase}.staging-*"))
    if target.exists() or claim.exists() or abandoned:
        raise AcceptanceError(f"phase {phase} cannot be reused")
    try:
        with claim.open("xb") as handle:
            handle.write(f"{CYCLE_ID} {phase}\n".encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise AcceptanceError(f"phase {phase} cannot be reused") from exc
    staging = evidence_root / f".{phase}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _publish_stage(staging: Path, target: Path) -> None:
    if target.exists():
        raise AcceptanceError(f"refusing to overwrite phase artifacts: {target.name}")
    os.rename(staging, target)


def _phase_scan_paths(staging: Path, *, evidence_root: Path) -> list[Path]:
    return [
        *_source_paths(evidence_root=evidence_root),
        *_artifact_files(staging),
    ]


def _assert_stage_secret_free(
    staging: Path,
    *,
    evidence_root: Path,
    redactor: ExactRedactor,
) -> dict[str, Any]:
    for path in _artifact_files(staging):
        if path.suffix.lower() == ".json":
            _metadata_only_json(_read_json(path), location=path.name)
    paths = _phase_scan_paths(staging, evidence_root=evidence_root)
    exact = scan_exact_secrets(paths, exact_values=redactor.exact_values)
    generic = scan_generic_secrets(paths)
    if exact["status"] != "passed" or generic["status"] != "passed":
        raise SecretLeakError("new source or staged artifact failed secret scan")
    return {"exact": exact, "generic": generic}


def _verify_completed_artifacts(
    state: dict[str, Any], *, evidence_root: Path
) -> None:
    for phase in PHASES[:-1]:
        phase_state = state.get("phases", {}).get(phase, {})
        if phase_state.get("status") != "passed":
            continue
        expected = phase_state.get("artifact_tree")
        phase_root = evidence_root / phase
        claim = evidence_root / f".{phase}.claim"
        if (
            not isinstance(expected, dict)
            or not phase_root.is_dir()
            or not claim.is_file()
        ):
            raise AcceptanceError(f"completed phase artifacts are missing: {phase}")
        if _tree_hash(phase_root) != expected:
            raise AcceptanceError(f"completed phase artifacts drifted: {phase}")


def _mark_phase_running(
    *,
    evidence_root: Path,
    state: dict[str, Any],
    phase: str,
    attempt_id: str,
) -> None:
    state["phases"][phase] = {
        "status": "running",
        "started_at": _now(),
        "attempt_id": attempt_id,
    }
    _save_state(evidence_root, state)


def _copy_metadata_json(source: Path, target: Path) -> dict[str, Any]:
    value = _read_json(source)
    _metadata_only_json(value)
    _atomic_json(target, value)
    return value


def _run_offline_phase(
    *,
    evidence_root: Path,
    state: dict[str, Any],
    redactor: ExactRedactor,
    user_root: Path,
    previous_evidence_root: Path,
    runner: CommandRunner = _default_command_runner,
) -> dict[str, Any]:
    _require_phase(state, "offline")
    staging = _stage_dir(evidence_root, "offline")
    attempt_id = f"offline_{uuid.uuid4().hex}"
    starting_source = _source_tree_hash(evidence_root=evidence_root)
    checks: list[dict[str, Any]] = []
    source_stable = True
    secret_scan_failed = False
    try:
        _mark_phase_running(
            evidence_root=evidence_root,
            state=state,
            phase="offline",
            attempt_id=attempt_id,
        )
        with tempfile.TemporaryDirectory(prefix="final-long-offline-") as work:
            work_root = Path(work)
            for name, command in _offline_external_commands(work_root):
                execution = runner(command, ROOT)
                recorded_smoke = name in {
                    "recorded_author_smoke",
                    "recorded_long_30x2_smoke",
                }
                check = _record_execution(
                    execution,
                    log_path=staging / "logs" / f"{name}.log",
                    redactor=redactor,
                    metadata_only=recorded_smoke,
                )
                check["name"] = name
                if name == "recorded_author_smoke" and execution.returncode == 0:
                    try:
                        recorded = json.loads(execution.stdout)
                        _metadata_only_json(recorded)
                        _atomic_json(staging / "recorded-author" / "result.json", recorded)
                    except (json.JSONDecodeError, AcceptanceError, TypeError):
                        check["status"] = "failed"
                        check["artifact_contract"] = "invalid"
                if name == "recorded_long_30x2_smoke" and execution.returncode == 0:
                    long_root = work_root / "recorded-long-output"
                    try:
                        summary = _copy_metadata_json(
                            long_root / "summary.json",
                            staging / "recorded-long-30x2" / "summary.json",
                        )
                        evidence = _copy_metadata_json(
                            long_root / "evidence.json",
                            staging / "recorded-long-30x2" / "evidence.json",
                        )
                        if not all(summary.get("gates", {}).values()) or not all(
                            evidence.get("gates", {}).values()
                        ):
                            check["status"] = "failed"
                    except (OSError, ValueError, AcceptanceError, json.JSONDecodeError):
                        check["status"] = "failed"
                        check["artifact_contract"] = "invalid"
                current_source = _source_tree_hash(evidence_root=evidence_root)
                check["source_tree_sha256_after"] = current_source
                if current_source != starting_source:
                    check["status"] = "failed"
                    source_stable = False
                checks.append(check)

        scan_paths = _phase_scan_paths(staging, evidence_root=evidence_root)
        exact = scan_exact_secrets(
            scan_paths,
            exact_values=redactor.exact_values,
        )
        checks.append({"name": "exact_secret_scan", **exact})
        generic = scan_generic_secrets(scan_paths)
        checks.append({"name": "generic_secret_scan", **generic})
        untracked = _untracked_sensitive_files(user_root=user_root)
        checks.append({"name": "untracked_sensitive_files", **untracked})
        if [item["name"] for item in checks] != list(OFFLINE_CHECK_NAMES):
            raise AcceptanceError("offline checks did not execute in the frozen order")
        final_source = _source_tree_hash(evidence_root=evidence_root)
        if final_source != starting_source:
            source_stable = False
        ending_identity = _repo_identity(evidence_root=evidence_root)
        if (
            ending_identity["branch"] != state["git"]["branch"]
            or ending_identity["head"] != state["git"]["head"]
            or ending_identity["source_tree_sha256"] != starting_source
        ):
            source_stable = False
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
        status = (
            "passed"
            if source_stable and all(item.get("status") == "passed" for item in checks)
            else "failed"
        )
        receipt = {
            "schema_version": "final-long-offline-v1",
            "phase": "offline",
            "attempt_id": attempt_id,
            "status": status,
            "created_at": _now(),
            "source_tree_sha256": starting_source,
            "source_tree_unchanged": source_stable,
            "check_count": len(checks),
            "checks": checks,
        }
        _metadata_only_json(receipt)
        _atomic_json(staging / "receipt.json", receipt)
        try:
            scans = _assert_stage_secret_free(
                staging,
                evidence_root=evidence_root,
                redactor=redactor,
            )
        except SecretLeakError:
            secret_scan_failed = True
            raise
        receipt["publication_scan"] = scans
        _atomic_json(staging / "receipt.json", receipt)
        _publish_stage(staging, evidence_root / "offline")
        if _source_tree_hash(evidence_root=evidence_root) != starting_source:
            raise AcceptanceError("source changed while publishing offline evidence")
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
    except BaseException as exc:
        secret_scan_failed = secret_scan_failed or isinstance(exc, SecretLeakError)
        if staging.exists():
            shutil.rmtree(staging)
        state["phases"]["offline"] = {
            "status": "failed",
            "failed_at": _now(),
            "reason": (
                "secret_scan_failed" if secret_scan_failed else "offline_execution_failed"
            ),
        }
        _save_state(evidence_root, state)
        raise

    state["phases"]["offline"] = {
        "status": receipt["status"],
        "completed_at": _now(),
        "attempt_id": attempt_id,
        "receipt": "offline/receipt.json",
        "source_tree_sha256": starting_source,
        "artifact_tree": _tree_hash(evidence_root / "offline"),
    }
    if receipt["status"] == "passed":
        state["authorized_source_tree_sha256"] = starting_source
        state["authorized_head"] = state["git"]["head"]
    _save_state(evidence_root, state)
    return receipt


def _real_phase_precheck(
    *,
    phase: str,
    evidence_root: Path,
    state: dict[str, Any],
    user_root: Path,
    previous_evidence_root: Path,
) -> dict[str, str]:
    _require_phase(state, phase)
    _verify_protected(
        state["protected"],
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )
    return _verify_authorized_source(state, evidence_root=evidence_root)


def _observed_probe_runtime(stdout: str) -> dict[str, Any]:
    for line in stdout.splitlines():
        if not line.startswith("[RUNTIME] "):
            continue
        try:
            value = json.loads(line.removeprefix("[RUNTIME] "))
        except json.JSONDecodeError:
            return {}
        if not isinstance(value, dict):
            return {}
        allowed = {
            "provider",
            "model",
            "source",
            "thinking_mode",
            "retries",
            "credential_present",
            "config_fingerprint",
        }
        return {key: value[key] for key in allowed & value.keys()}
    return {}


def _probe_contract_passes(stdout: str, *, config: Any) -> tuple[bool, dict[str, Any]]:
    observed = _observed_probe_runtime(stdout)
    expected = _safe_provider(config)
    runtime_ok = bool(
        observed.get("provider") == EXPECTED_PROVIDER
        and observed.get("model") == EXPECTED_MODEL
        and observed.get("source") == "provider_file"
        and observed.get("thinking_mode") == EXPECTED_THINKING_MODE
        and observed.get("retries") == EXPECTED_SDK_RETRIES
        and observed.get("credential_present") is True
        and observed.get("config_fingerprint") == expected.get("config_fingerprint")
    )
    call_ok = bool(re.search(r"(?m)^\[OK\] quota healthy\.", stdout))
    return runtime_ok and call_ok, observed


def _run_probe_phase(
    *,
    evidence_root: Path,
    state: dict[str, Any],
    redactor: ExactRedactor,
    config: Any,
    provider_file: Path,
    user_root: Path,
    previous_evidence_root: Path,
    runner: CommandRunner = _default_command_runner,
) -> dict[str, Any]:
    identity = _real_phase_precheck(
        phase="probe",
        evidence_root=evidence_root,
        state=state,
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )
    staging = _stage_dir(evidence_root, "probe")
    attempt_id = f"probe_{uuid.uuid4().hex}"
    try:
        _mark_phase_running(
            evidence_root=evidence_root,
            state=state,
            phase="probe",
            attempt_id=attempt_id,
        )
        command = [
            sys.executable,
            "scripts/probe_quota.py",
            "--provider-file",
            str(provider_file.resolve()),
            "--provider",
            EXPECTED_PROVIDER,
            "--expect-model",
            EXPECTED_MODEL,
            "--expect-thinking-mode",
            EXPECTED_THINKING_MODE,
            "--expect-max-retries",
            str(EXPECTED_SDK_RETRIES),
        ]
        execution = runner(command, ROOT)
        run = _record_execution(
            execution,
            log_path=staging / "probe-run.json",
            redactor=redactor,
            metadata_only=True,
        )
        probe_contract, observed_runtime = _probe_contract_passes(
            execution.stdout, config=config
        )
        passed = execution.returncode == 0 and probe_contract
        if _source_tree_hash(evidence_root=evidence_root) != identity["source_tree_sha256"]:
            raise AcceptanceError("source changed during Provider probe")
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
        receipt = {
            "schema_version": "final-long-provider-probe-v1",
            "phase": "probe",
            "attempt_id": attempt_id,
            "status": "passed" if passed else "failed",
            "created_at": _now(),
            "source_tree_sha256": identity["source_tree_sha256"],
            "head": identity["head"],
            "provider_runtime": _safe_provider(config),
            "observed_runtime": observed_runtime,
            "execution": run,
            "contract": {
                "provider": EXPECTED_PROVIDER,
                "model": EXPECTED_MODEL,
                "thinking_mode": EXPECTED_THINKING_MODE,
                "sdk_retries": EXPECTED_SDK_RETRIES,
                "minimum_call_count": 1,
            },
        }
        _atomic_json(staging / "receipt.json", receipt)
        _assert_stage_secret_free(staging, evidence_root=evidence_root, redactor=redactor)
        _publish_stage(staging, evidence_root / "probe")
        if _source_tree_hash(evidence_root=evidence_root) != identity["source_tree_sha256"]:
            raise AcceptanceError("source changed while publishing Provider probe")
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
    except BaseException as exc:
        if staging.exists():
            shutil.rmtree(staging)
        state["phases"]["probe"] = {
            "status": "failed",
            "failed_at": _now(),
            "attempt_id": attempt_id,
            "reason": (
                "secret_scan_failed"
                if isinstance(exc, SecretLeakError)
                else "probe_execution_failed"
            ),
        }
        _save_state(evidence_root, state)
        raise
    state["phases"]["probe"] = {
        "status": receipt["status"],
        "completed_at": _now(),
        "attempt_id": attempt_id,
        "receipt": "probe/receipt.json",
        "artifact_tree": _tree_hash(evidence_root / "probe"),
    }
    _save_state(evidence_root, state)
    return receipt


_SECTION_EVIDENCE_KEYS = {
    "section_id",
    "transaction_id",
    "phase",
    "committed",
    "story_bible_revision",
    "canonical_revision_before",
    "canonical_revision_after",
    "canonical_revision",
    "provider",
    "model",
    "contract_hash",
    "context_contract_hash",
    "execution_spec_hash",
    "narrative_contract_pass",
    "narrative_violation_codes",
    "required_events_completed",
    "required_events_total",
    "end_states_reached",
    "end_states_total",
    "canonical_state_sha256",
    "delta_count",
    "committed_delta_count",
    "rejected_delta_count",
    "validated_delta_count",
    "dropped_delta_count",
    "dropped_thread_change_count",
    "proposal_drop_codes",
    "evidenceless_state_delta_commits",
    "illegal_thread_change_commits",
    "state_conflict_count",
    "state_violation_codes",
    "stale_context_count",
    "recovery_count",
    "thread_liveness_violations",
    "style_contract_pass",
    "style_rewrite_rate",
    "initial_narrative_length",
    "narrative_length",
    "writer_block_nonspace_lengths",
    "writer_cell_nonspace_lengths",
    "writer_cell_sentence_boundary_counts",
    "prompt_tokens",
    "completion_tokens",
    "planner_tokens",
    "retry_tokens",
    "repair_tokens",
    "total_tokens",
    "latency_seconds",
    "provider_errors",
    "retry_count",
    "writer_retry_performed",
    "writer_first_pass_pass",
    "repair_performed",
    "repair_success",
    "repair_audit_codes",
    "repair_patch_codes",
    "repair_patch_nonspace_lengths",
    "repair_patch_total_nonspace_chars",
    "repair_patch_max_nonspace_chars",
    "planner_calls",
    "writer_calls",
    "structured_output_repair_count",
    "runtime_provider",
    "runtime_provider_model",
    "runtime_provider_source",
    "runtime_provider_config_fingerprint",
}

_MATRIX_SUMMARY_KEYS = {
    "attempted",
    "committed",
    "contract_pass",
    "writer_first_pass_pass",
    "writer_retries",
    "repairs",
    "repair_success",
    "provider_calls",
    "provider_errors",
    "planner_calls",
    "prompt_tokens",
    "completion_tokens",
    "planner_tokens",
    "retry_tokens",
    "repair_tokens",
    "total_tokens",
    "mean_latency_seconds",
    "hard_fact_error_commits",
    "state_conflict_commits",
    "illegal_thread_change_commits",
    "evidenceless_state_delta_commits",
    "length_in_range_count",
    "length_in_range_rate",
}

_CODE_LIST_KEYS = {
    "narrative_violation_codes",
    "proposal_drop_codes",
    "state_violation_codes",
    "repair_audit_codes",
    "repair_patch_codes",
}
_INTEGER_LIST_KEY_LENGTHS = {
    "repair_patch_nonspace_lengths": (0, 8),
    "writer_block_nonspace_lengths": (0, 10),
    "writer_cell_nonspace_lengths": (0, 52),
    "writer_cell_sentence_boundary_counts": (0, 52),
}


def _safe_codes(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise AcceptanceError("matrix evidence code list is malformed")
    codes = [str(item) for item in value]
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", item) for item in codes):
        raise AcceptanceError("matrix evidence contains a non-code value")
    return codes


def _safe_integer_list(value: Any, *, key: str) -> list[int]:
    if not isinstance(value, list):
        raise AcceptanceError(f"matrix evidence {key} is malformed")
    values = [
        item
        for item in value
        if isinstance(item, int) and not isinstance(item, bool) and item >= 0
    ]
    if len(values) != len(value):
        raise AcceptanceError(f"matrix evidence {key} is malformed")
    minimum, maximum = _INTEGER_LIST_KEY_LENGTHS[key]
    if not minimum <= len(values) <= maximum:
        raise AcceptanceError(f"matrix evidence {key} has invalid cardinality")
    if key.startswith("writer_") and values and len(values) != maximum:
        raise AcceptanceError(f"matrix evidence {key} has invalid cardinality")
    return values


def _matrix_identifier(value: Any) -> str:
    """Accept only a nonblank JSON string as an evidence identifier."""

    return value.strip() if isinstance(value, str) else ""


def _safe_matrix_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AcceptanceError("matrix summary is malformed")
    return {key: value[key] for key in sorted(_MATRIX_SUMMARY_KEYS & value.keys())}


_FAILURE_EVIDENCE_KEYS = {
    "section",
    "attempt",
    "provider_failure",
    "provider_code",
    "provider_http_category",
    "provider_stage",
    "planner_calls",
    "writer_calls",
    "structured_output_repair_count",
    "provider_call_count",
    "provider_call_count_known",
    "transaction_phase",
    "runtime_provider",
    "runtime_provider_model",
    "runtime_provider_source",
    "runtime_provider_config_fingerprint",
}
_PROVIDER_FAILURE_CATEGORY_BY_CODE = {
    "PROVIDER_AUTH_FAILED": "auth",
    "PROVIDER_RATE_LIMITED": "rate_limit",
    "PROVIDER_REQUEST_INVALID": "request_invalid",
    "PROVIDER_TIMEOUT": "timeout",
    "PROVIDER_UNAVAILABLE": "unavailable",
    "PROVIDER_OUTPUT_INVALID": "output_invalid",
}
_PROVIDER_FAILURE_STAGES = {
    "planner",
    "writer",
    "writer_json_repair",
    "repair",
    "repair_json_repair",
}
_FAILURE_RUNTIME_FIELDS = {
    "runtime_provider": "provider",
    "runtime_provider_model": "model",
    "runtime_provider_source": "source",
    "runtime_provider_config_fingerprint": "config_fingerprint",
}


def _safe_matrix_failure(
    value: Any,
    *,
    expected_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AcceptanceError("matrix failure evidence is malformed")
    row = {
        key: value[key]
        for key in sorted(_FAILURE_EVIDENCE_KEYS & value.keys())
    }
    for key in ("section", "attempt"):
        value_int = row.get(key)
        if (
            not isinstance(value_int, int)
            or isinstance(value_int, bool)
            or value_int < 1
        ):
            raise AcceptanceError("matrix failure ordinal is malformed")
    provider_failure = row.get("provider_failure")
    if not isinstance(provider_failure, bool):
        raise AcceptanceError("matrix failure classification is malformed")
    count_limits = {
        "planner_calls": 1,
        "writer_calls": 3,
        "structured_output_repair_count": 2,
        "provider_call_count": 6,
    }
    for key, maximum in count_limits.items():
        count = row.get(key)
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 0 <= count <= maximum
        ):
            raise AcceptanceError("matrix failure call count is malformed")
    count_known = row.get("provider_call_count_known")
    if not isinstance(count_known, bool):
        raise AcceptanceError("matrix failure call-count authority is malformed")
    decomposed = (
        row["planner_calls"]
        + row["writer_calls"]
        + row["structured_output_repair_count"]
    )
    if row["provider_call_count"] != decomposed:
        raise AcceptanceError("matrix failure call count does not decompose")
    if count_known != (decomposed > 0):
        raise AcceptanceError("matrix failure call-count authority is inconsistent")
    phase = str(row.get("transaction_phase", "") or "")
    if phase and phase != "failed":
        raise AcceptanceError("matrix failure transaction phase is invalid")

    runtime_present = {
        field: str(row.get(field, "") or "") for field in _FAILURE_RUNTIME_FIELDS
    }
    has_runtime = [bool(value) for value in runtime_present.values()]
    if any(has_runtime) and not all(has_runtime):
        raise AcceptanceError("matrix failure runtime receipt is incomplete")
    if count_known and not all(has_runtime):
        raise AcceptanceError("matrix counted failure lacks a runtime receipt")
    if runtime_present["runtime_provider"] and not re.fullmatch(
        r"[a-z0-9][a-z0-9_.-]{0,63}",
        runtime_present["runtime_provider"],
    ):
        raise AcceptanceError("matrix failure provider identity is malformed")
    if runtime_present["runtime_provider_model"] and (
        not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._+:/@-]{0,191}",
            runtime_present["runtime_provider_model"],
        )
        or "://" in runtime_present["runtime_provider_model"]
    ):
        raise AcceptanceError("matrix failure provider model is malformed")
    if runtime_present["runtime_provider_source"] and not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_.-]{0,63}",
        runtime_present["runtime_provider_source"],
    ):
        raise AcceptanceError("matrix failure provider source is malformed")
    fingerprint = runtime_present["runtime_provider_config_fingerprint"]
    if fingerprint and not re.fullmatch(r"[0-9a-f]{16}", fingerprint):
        raise AcceptanceError("matrix failure evidence contains an invalid fingerprint")
    if expected_runtime is not None and all(has_runtime):
        for observed_field, expected_field in _FAILURE_RUNTIME_FIELDS.items():
            if runtime_present[observed_field] != str(
                expected_runtime.get(expected_field, "") or ""
            ):
                raise AcceptanceError("matrix failure runtime receipt drifted")

    if provider_failure:
        code = str(row.get("provider_code", "") or "")
        category = str(row.get("provider_http_category", "") or "")
        stage = str(row.get("provider_stage", "") or "")
        if _PROVIDER_FAILURE_CATEGORY_BY_CODE.get(code) != category:
            raise AcceptanceError("matrix failure provider contract is invalid")
        if stage not in _PROVIDER_FAILURE_STAGES:
            raise AcceptanceError("matrix failure provider stage is invalid")
        if not count_known or not all(has_runtime) or phase != "failed":
            raise AcceptanceError("matrix provider failure evidence is incomplete")
        if stage == "planner" and (
            row["planner_calls"] != 1 or row["writer_calls"] != 0
        ):
            raise AcceptanceError("matrix planner failure counts are invalid")
        if stage != "planner" and row["writer_calls"] < 1:
            raise AcceptanceError("matrix writer failure counts are invalid")
        if stage in {"writer_json_repair", "repair_json_repair"} and row[
            "structured_output_repair_count"
        ] < 1:
            raise AcceptanceError("matrix JSON-repair failure counts are invalid")
    elif any(
        row.get(key)
        for key in ("provider_code", "provider_http_category", "provider_stage")
    ):
        raise AcceptanceError("non-provider failure claims provider metadata")
    _metadata_only_json(row)
    return row


def _sanitize_matrix(
    matrix: dict[str, Any],
    *,
    expected_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    combinations = []
    for combination in matrix.get("combinations", []):
        sections = []
        for section in combination.get("sections", []):
            row = {
                key: section[key]
                for key in sorted(
                    (
                        _SECTION_EVIDENCE_KEYS
                        - _CODE_LIST_KEYS
                        - _INTEGER_LIST_KEY_LENGTHS.keys()
                    )
                    & section.keys()
                )
            }
            for key in sorted(_CODE_LIST_KEYS & section.keys()):
                row[key] = _safe_codes(section[key])
            for key in sorted(_INTEGER_LIST_KEY_LENGTHS.keys() & section.keys()):
                row[key] = _safe_integer_list(section[key], key=key)
            sections.append(row)
        integrity = _safe_codes(combination.get("integrity", []))
        failures = [
            _safe_matrix_failure(item, expected_runtime=expected_runtime)
            for item in combination.get("failures", [])
        ]
        combinations.append(
            {
                "run_id": combination.get("run_id", ""),
                "theme": combination.get("theme", ""),
                "style": combination.get("style", ""),
                "summary": _safe_matrix_summary(combination.get("summary", {})),
                "integrity": integrity,
                "sections": sections,
                "failure_count": len(failures),
                "failures": failures,
            }
        )
    sanitized = {
        "schema_version": "final-long-matrix-evidence-v1",
        "config": {
            key: matrix.get("config", {}).get(key)
            for key in (
                "themes",
                "styles",
                "seed",
                "provider",
                "model",
                "thinking_mode",
                "sections_per_combo",
                "desired_length",
                "checkpoint_every",
                "runtime_rebuild_every",
                "id_namespace",
            )
        },
        "evidence_boundary": {
            key: matrix.get("evidence_boundary", {}).get(key)
            for key in (
                "deterministic",
                "recorded",
                "real_provider",
                "human_review",
                "llm_judge",
            )
        },
        "summary": _safe_matrix_summary(matrix.get("summary", {})),
        "combinations": combinations,
        "raw_prose_persisted": False,
        "raw_response_persisted": False,
    }
    _metadata_only_json(sanitized)
    return sanitized


def assess_matrix(
    stage: str,
    matrix: dict[str, Any],
    *,
    expected_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in {"g1", "g2"}:
        raise AcceptanceError(f"invalid matrix stage: {stage}")
    from scripts.run_p6_length_anchor_recovery import assess_g1, assess_g2

    result = (assess_g1(matrix) if stage == "g1" else assess_g2(matrix)).copy()
    checks = dict(result.get("checks", {}))
    metrics = dict(result.get("metrics", {}))
    summary_anomalies = list(
        matrix.get("summary", {}).get("data_integrity_violations", [])
    )
    combination_anomalies = [
        code
        for combination in matrix.get("combinations", [])
        for code in combination.get("integrity", [])
    ]
    sections = [
        section
        for combination in matrix.get("combinations", [])
        for section in combination.get("sections", [])
    ]
    failures = [
        failure
        for combination in matrix.get("combinations", [])
        for failure in combination.get("failures", [])
    ]
    validated_failures = [
        _safe_matrix_failure(failure, expected_runtime=expected_runtime)
        for failure in failures
    ]
    transaction_ids = [
        _matrix_identifier(section.get("transaction_id")) for section in sections
    ]
    section_ids = [
        _matrix_identifier(section.get("section_id")) for section in sections
    ]
    direct_anomaly_count = (
        sum(not value for value in transaction_ids)
        + len(transaction_ids)
        - len(set(transaction_ids))
        + sum(not value for value in section_ids)
        + len(section_ids)
        - len(set(section_ids))
    )
    anomaly_count = (
        len(summary_anomalies) + len(combination_anomalies) + direct_anomaly_count
    )
    checks["transaction_anomalies_zero"] = anomaly_count == 0
    metrics["transaction_anomalies"] = anomaly_count
    metrics["direct_identifier_anomalies"] = direct_anomaly_count
    provider_failure_rows = sum(
        bool(failure.get("provider_failure"))
        for failure in validated_failures
    )
    section_provider_calls = sum(
        int(section.get("planner_calls", 0))
        + int(section.get("writer_calls", 0))
        + int(section.get("structured_output_repair_count", 0))
        for section in sections
    )
    failure_provider_calls = sum(
        int(failure["provider_call_count"])
        for failure in validated_failures
    )
    observed_provider_calls = section_provider_calls + failure_provider_calls
    observed_planner_calls = sum(
        int(section.get("planner_calls", 0)) for section in sections
    ) + sum(int(failure["planner_calls"]) for failure in validated_failures)
    checks["failure_rows_zero"] = not validated_failures
    checks["provider_error_summary_matches_failure_rows"] = (
        int(matrix.get("summary", {}).get("provider_errors", 0))
        == provider_failure_rows
    )
    checks["provider_call_accounting_matches"] = (
        int(matrix.get("summary", {}).get("provider_calls", -1))
        == observed_provider_calls
    )
    checks["planner_call_accounting_matches"] = (
        int(matrix.get("summary", {}).get("planner_calls", -1))
        == observed_planner_calls
    )
    metrics["failure_rows"] = len(validated_failures)
    metrics["provider_failure_rows"] = provider_failure_rows
    metrics["provider_calls_recomputed"] = observed_provider_calls
    metrics["planner_calls_recomputed"] = observed_planner_calls
    if expected_runtime is not None:
        expected_receipt = {
            "runtime_provider": expected_runtime.get("provider"),
            "runtime_provider_model": expected_runtime.get("model"),
            "runtime_provider_source": expected_runtime.get("source"),
            "runtime_provider_config_fingerprint": expected_runtime.get(
                "config_fingerprint"
            ),
        }
        if any(value in (None, "") for value in expected_receipt.values()):
            raise AcceptanceError("expected provider runtime receipt is incomplete")
        receipt_rows = [
            *sections,
            *[
                failure
                for failure in validated_failures
                if failure.get("provider_call_count_known")
            ],
        ]
        missing_fields = sum(
            field not in row or row.get(field) in (None, "")
            for row in receipt_rows
            for field in expected_receipt
        )
        mismatched_receipts = sum(
            any(row.get(field) != expected for field, expected in expected_receipt.items())
            for row in receipt_rows
        )
        checks["runtime_receipts_match_expected"] = (
            bool(receipt_rows)
            and missing_fields == 0
            and mismatched_receipts == 0
        )
        metrics["runtime_receipts_checked"] = len(receipt_rows)
        metrics["runtime_receipt_missing_fields"] = missing_fields
        metrics["runtime_receipt_mismatches"] = mismatched_receipts
    return {
        **result,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "metrics": metrics,
    }


def _matrix_identity_passes(stage: str, matrix: dict[str, Any]) -> bool:
    config = matrix.get("config", {})
    expected_styles = ["literary"] if stage == "g1" else list(HISTORICAL_STYLES)
    expected_sections = 1 if stage == "g1" else 3
    combinations = matrix.get("combinations", [])
    expected_pairs = {("action_conflict", style) for style in expected_styles}
    actual_pairs = [
        (str(item.get("theme", "")), str(item.get("style", "")))
        for item in combinations
    ]
    run_ids = [_matrix_identifier(item.get("run_id")) for item in combinations]
    topology_passed = bool(
        len(combinations) == len(expected_pairs)
        and set(actual_pairs) == expected_pairs
        and len(actual_pairs) == len(set(actual_pairs))
        and all(
            len(combination.get("sections", [])) == expected_sections
            for combination in combinations
        )
        and all(run_ids)
        and len(run_ids) == len(set(run_ids))
    )
    return bool(
        config.get("themes") == ["action_conflict"]
        and config.get("styles") == expected_styles
        and config.get("sections_per_combo") == expected_sections
        and config.get("desired_length") == 900
        and config.get("provider") == EXPECTED_PROVIDER
        and config.get("model") == EXPECTED_MODEL
        and config.get("thinking_mode") == EXPECTED_THINKING_MODE
        and config.get("seed") == 20260727
        and config.get("checkpoint_every") == 1
        and config.get("runtime_rebuild_every") == 2
        and config.get("id_namespace") == stage
        and topology_passed
    )


def _run_matrix_phase(
    *,
    phase: str,
    evidence_root: Path,
    state: dict[str, Any],
    redactor: ExactRedactor,
    config: Any,
    provider_file: Path,
    user_root: Path,
    previous_evidence_root: Path,
    runner: CommandRunner = _default_command_runner,
) -> dict[str, Any]:
    identity = _real_phase_precheck(
        phase=phase,
        evidence_root=evidence_root,
        state=state,
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )
    staging = _stage_dir(evidence_root, phase)
    attempt_id = f"{phase}_{uuid.uuid4().hex}"
    try:
        _mark_phase_running(
            evidence_root=evidence_root,
            state=state,
            phase=phase,
            attempt_id=attempt_id,
        )
        with tempfile.TemporaryDirectory(prefix=f"final-long-{phase}-") as work:
            raw_output = Path(work) / "matrix-output"
            styles = "literary" if phase == "g1" else ",".join(HISTORICAL_STYLES)
            sections = "1" if phase == "g1" else "3"
            command = [
                sys.executable,
                "scripts/run_author_stage1_matrix.py",
                "--provider-file",
                str(provider_file.resolve()),
                "--model",
                EXPECTED_MODEL,
                "--id-namespace",
                phase,
                "--themes",
                "action_conflict",
                "--styles",
                styles,
                "--sections-per-combo",
                sections,
                "--checkpoint-every",
                "1",
                "--runtime-rebuild-every",
                "2",
                "--combo-retries",
                "0",
                "--desired-length",
                "900",
                "--seed",
                "20260727",
                "--output-dir",
                str(raw_output),
            ]
            execution = runner(command, ROOT)
            run = _record_execution(
                execution,
                log_path=staging / "provider-run.json",
                redactor=redactor,
                metadata_only=True,
            )
            matrix_path = raw_output / "stage1-matrix.json"
            matrix = _read_json(matrix_path) if matrix_path.is_file() else {}
            assessment = assess_matrix(
                phase,
                matrix,
                expected_runtime=_safe_provider(config),
            )
            if phase == "g2":
                g1_evidence = _read_json(evidence_root / "g1" / "matrix-evidence.json")
                g1_combinations = g1_evidence.get("combinations", [])
                current_combinations = matrix.get("combinations", [])
                identifier_sets = {
                    "run": (
                        {
                            value
                            for combination in g1_combinations
                            if (
                                value := _matrix_identifier(
                                    combination.get("run_id")
                                )
                            )
                        },
                        {
                            value
                            for combination in current_combinations
                            if (
                                value := _matrix_identifier(
                                    combination.get("run_id")
                                )
                            )
                        },
                    ),
                    "transaction": (
                        {
                            value
                            for combination in g1_combinations
                            for section in combination.get("sections", [])
                            if (
                                value := _matrix_identifier(
                                    section.get("transaction_id")
                                )
                            )
                        },
                        {
                            value
                            for combination in current_combinations
                            for section in combination.get("sections", [])
                            if (
                                value := _matrix_identifier(
                                    section.get("transaction_id")
                                )
                            )
                        },
                    ),
                    "section": (
                        {
                            value
                            for combination in g1_combinations
                            for section in combination.get("sections", [])
                            if (
                                value := _matrix_identifier(
                                    section.get("section_id")
                                )
                            )
                        },
                        {
                            value
                            for combination in current_combinations
                            for section in combination.get("sections", [])
                            if (
                                value := _matrix_identifier(
                                    section.get("section_id")
                                )
                            )
                        },
                    ),
                }
                metric_names = {
                    "run": "runs_reused_from_g1",
                    "transaction": "transactions_reused_from_g1",
                    "section": "sections_reused_from_g1",
                }
                for identifier_type, (g1_ids, current_ids) in identifier_sets.items():
                    reused = g1_ids & current_ids
                    assessment["checks"][
                        f"{identifier_type}_reuse_with_g1_zero"
                    ] = not reused
                    assessment["metrics"][metric_names[identifier_type]] = len(
                        reused
                    )
                assessment["status"] = (
                    "passed" if all(assessment["checks"].values()) else "failed"
                )
            identity_passed = _matrix_identity_passes(phase, matrix)
            status = (
                "passed"
                if execution.returncode == 0
                and assessment["status"] == "passed"
                and identity_passed
                else "failed"
            )
            sanitized = _sanitize_matrix(
                matrix,
                expected_runtime=_safe_provider(config),
            )
            _atomic_json(staging / "matrix-evidence.json", sanitized)
            _atomic_json(staging / "assessment.json", assessment)
            raw_sha = _sha256_file(matrix_path) if matrix_path.is_file() else ""
        if _source_tree_hash(evidence_root=evidence_root) != identity["source_tree_sha256"]:
            raise AcceptanceError("source changed during real matrix phase")
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
        receipt = {
            "schema_version": f"final-long-{phase}-v1",
            "phase": phase,
            "attempt_id": attempt_id,
            "status": status,
            "created_at": _now(),
            "source_tree_sha256": identity["source_tree_sha256"],
            "head": identity["head"],
            "provider_runtime": _safe_provider(config),
            "execution": run,
            "matrix_identity_passed": identity_passed,
            "raw_matrix_sha256": raw_sha,
            "raw_matrix_persisted": False,
            "assessment": assessment,
        }
        _atomic_json(staging / "receipt.json", receipt)
        _assert_stage_secret_free(staging, evidence_root=evidence_root, redactor=redactor)
        _publish_stage(staging, evidence_root / phase)
        if _source_tree_hash(evidence_root=evidence_root) != identity["source_tree_sha256"]:
            raise AcceptanceError("source changed while publishing real matrix evidence")
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
    except BaseException as exc:
        if staging.exists():
            shutil.rmtree(staging)
        state["phases"][phase] = {
            "status": "failed",
            "failed_at": _now(),
            "attempt_id": attempt_id,
            "reason": (
                "secret_scan_failed"
                if isinstance(exc, SecretLeakError)
                else "matrix_execution_failed"
            ),
        }
        _save_state(evidence_root, state)
        raise
    state["phases"][phase] = {
        "status": receipt["status"],
        "completed_at": _now(),
        "attempt_id": attempt_id,
        "receipt": f"{phase}/receipt.json",
        "artifact_tree": _tree_hash(evidence_root / phase),
    }
    _save_state(evidence_root, state)
    return receipt


def _validate_product_evidence(evidence: dict[str, Any]) -> bool:
    _metadata_only_json(evidence)
    exact_keys = {
        "schema_version",
        "outcome",
        "provider_runtime",
        "outline",
        "job",
        "style_transition",
        "control",
        "metrics",
        "transactions",
        "chapters",
        "gates",
        "secret_scan",
        "artifacts",
    }
    nested_keys = {
        "provider_runtime": {
            "provider",
            "model",
            "source",
            "thinking_mode",
            "retries",
            "credential_present",
            "config_fingerprint",
            "key_fingerprint",
        },
        "outline": {
            "provider_calls",
            "repair_performed",
            "revision",
            "final_progress_revision",
            "chapter_count",
        },
        "job": {
            "job_id",
            "status",
            "revision",
            "prompt_tokens_total",
            "completion_tokens_total",
            "latency_total_ms",
            "repair_total",
            "retry_count",
            "active_transaction_id_present",
        },
        "style_transition": {
            "initial_style_profile_id",
            "custom_style_profile_id",
            "custom_style_revision",
            "custom_style_prompt_hash",
            "applies_from_chapter_ordinal",
            "sample_excluded_from_prompt",
        },
        "control": {"pause_count", "resume_count", "safe_boundary"},
        "metrics": {
            "chapter_count",
            "section_count",
            "transaction_count",
            "attempt_count",
            "planner_calls",
            "section_provider_calls",
            "provider_calls_total",
            "full_writer_retries",
            "repair_total",
            "duplicate_section_count",
            "duplicate_transaction_count",
            "rejected_prose_published_count",
            "canonical_revision_final",
            "production_event_count",
        },
        "secret_scan": {
            "exact_key_hits",
            "exact_base_url_hits",
            "generic_secret_hits",
        },
        "artifacts": {"manuscript_sha256", "manuscript_bytes"},
    }
    transaction_keys = {
        "transaction_id",
        "provider",
        "model",
        "source",
        "config_fingerprint",
        "structured_output_repair_count",
        "planner_calls",
        "writer_calls",
        "provider_calls",
        "full_writer_retry_count",
        "committed",
    }
    chapter_keys = {
        "chapter_id",
        "ordinal",
        "section_count",
        "char_count",
        "style_profile_id",
        "style_revision",
        "style_prompt_hash",
        "canonical_revision_start",
        "canonical_revision_end",
        "repair_total",
        "transaction_ids",
    }
    expected_gates = {
        "provider_contract",
        "three_committed_chapters",
        "single_section_per_chapter",
        "chapter_lengths_in_range",
        "style_applies_only_to_third",
        "planner_zero",
        "full_writer_retry_zero",
        "provider_call_accounting",
        "formal_transactions",
        "provider_receipts_bound_to_transactions",
        "attempts_committed_only",
        "no_rejected_prose_published",
        "unique_transactions_and_sections",
        "canonical_revision_contiguous",
        "outline_progress_committed",
        "no_job_retry",
        "pause_resume_once",
        "event_sequence_contiguous",
    }
    if set(evidence) != exact_keys:
        raise AcceptanceError("product evidence has an unexpected top-level schema")
    if any(
        not isinstance(evidence.get(key), dict)
        or set(evidence[key]) != allowed
        for key, allowed in nested_keys.items()
    ):
        raise AcceptanceError("product evidence has an unexpected nested schema")
    if (
        not isinstance(evidence.get("transactions"), list)
        or any(not isinstance(row, dict) or set(row) != transaction_keys for row in evidence["transactions"])
        or not isinstance(evidence.get("chapters"), list)
        or any(not isinstance(row, dict) or set(row) != chapter_keys for row in evidence["chapters"])
        or not isinstance(evidence.get("gates"), dict)
        or set(evidence["gates"]) != expected_gates
    ):
        raise AcceptanceError("product evidence has an unexpected row schema")
    runtime = evidence.get("provider_runtime", {})
    metrics = evidence.get("metrics", {})
    outline = evidence.get("outline", {})
    transactions = evidence.get("transactions", [])
    chapters = evidence.get("chapters", [])
    gates = evidence.get("gates", {})
    styles = [chapter.get("style_profile_id") for chapter in chapters]
    transaction_counts_valid = all(
        isinstance(row.get("planner_calls"), int)
        and not isinstance(row.get("planner_calls"), bool)
        and row["planner_calls"] == 0
        and isinstance(row.get("writer_calls"), int)
        and not isinstance(row.get("writer_calls"), bool)
        and 1 <= row["writer_calls"] <= 2
        and isinstance(row.get("structured_output_repair_count"), int)
        and not isinstance(row.get("structured_output_repair_count"), bool)
        and 0 <= row["structured_output_repair_count"] <= 1
        and isinstance(row.get("provider_calls"), int)
        and not isinstance(row.get("provider_calls"), bool)
        and row["provider_calls"]
        == row["planner_calls"]
        + row["writer_calls"]
        + row["structured_output_repair_count"]
        for row in transactions
    )
    observed_section_provider_calls = sum(
        int(row.get("provider_calls", -1)) for row in transactions
    )
    return bool(
        evidence.get("outcome") == "passed"
        and gates
        and all(gates.values())
        and runtime.get("provider") == EXPECTED_PROVIDER
        and runtime.get("model") == EXPECTED_MODEL
        and runtime.get("thinking_mode") == EXPECTED_THINKING_MODE
        and runtime.get("retries") == EXPECTED_SDK_RETRIES
        and int(metrics.get("chapter_count", 0)) >= 3
        and int(metrics.get("planner_calls", -1)) == 0
        and transaction_counts_valid
        and int(metrics.get("section_provider_calls", -1))
        == observed_section_provider_calls
        and int(metrics.get("provider_calls_total", -1))
        == int(outline.get("provider_calls", -1))
        + observed_section_provider_calls
        and int(metrics.get("full_writer_retries", -1)) == 0
        and int(metrics.get("duplicate_section_count", -1)) == 0
        and int(metrics.get("duplicate_transaction_count", -1)) == 0
        and int(metrics.get("rejected_prose_published_count", -1)) == 0
        and len(styles) >= 3
        and styles[0] == styles[1] == "preset_literary"
        and styles[2] != "preset_literary"
    )


def _assert_product_artifact_boundary(artifacts: Path) -> None:
    actual_files = {
        path.relative_to(artifacts).as_posix()
        for path in _artifact_files(artifacts)
    }
    allowed_files = {
        "manuscript.md",
        "evidence.json",
        "summary.json",
        "artifact-sha256.json",
    }
    if actual_files - allowed_files:
        raise AcceptanceError("product smoke emitted an unexpected artifact")


def _validate_product_artifacts(artifacts: Path, evidence: dict[str, Any]) -> bool:
    _assert_product_artifact_boundary(artifacts)
    if not _validate_product_evidence(evidence):
        return False
    manuscript = artifacts / "manuscript.md"
    evidence_path = artifacts / "evidence.json"
    summary_path = artifacts / "summary.json"
    hashes_path = artifacts / "artifact-sha256.json"
    actual_files = {
        path.relative_to(artifacts).as_posix()
        for path in _artifact_files(artifacts)
    }
    allowed_files = {
        "manuscript.md",
        "evidence.json",
        "summary.json",
        "artifact-sha256.json",
    }
    if actual_files != allowed_files:
        return False
    if not all(path.is_file() for path in (manuscript, evidence_path, summary_path, hashes_path)):
        return False
    if manuscript.stat().st_size == 0:
        return False
    declared_manuscript = evidence.get("artifacts", {}).get("manuscript_sha256")
    if str(declared_manuscript).upper() != _sha256_file(manuscript):
        return False
    try:
        summary = _read_json(summary_path)
        hashes_document = _read_json(hashes_path)
    except (AcceptanceError, OSError, ValueError, json.JSONDecodeError):
        return False
    if (
        set(summary)
        != {"schema_version", "ok", "provider", "metrics", "gates", "artifact_hashes"}
        or summary.get("ok") is not True
        or summary.get("provider") != evidence.get("provider_runtime")
        or summary.get("metrics") != evidence.get("metrics")
        or summary.get("gates") != evidence.get("gates")
        or set(summary.get("artifact_hashes", {})) != {"manuscript.md", "evidence.json"}
        or set(hashes_document) != {"schema_version", "artifacts"}
    ):
        raise AcceptanceError("product artifact metadata schema is malformed")
    if any(
        str(summary["artifact_hashes"].get(name, "")).upper()
        != _sha256_file(artifacts / name)
        for name in ("manuscript.md", "evidence.json")
    ):
        return False
    hashes = hashes_document.get("artifacts", {})
    expected_names = {"manuscript.md", "evidence.json", "summary.json"}
    if set(hashes) != expected_names:
        return False
    for name in expected_names:
        row = hashes.get(name, {})
        path = artifacts / name
        if (
            not isinstance(row, dict)
            or set(row) != {"sha256", "bytes"}
            or str(row.get("sha256", "")).upper() != _sha256_file(path)
            or row.get("bytes") != path.stat().st_size
        ):
            return False
    return True


def _run_product_phase(
    *,
    evidence_root: Path,
    state: dict[str, Any],
    redactor: ExactRedactor,
    config: Any,
    provider_file: Path,
    user_root: Path,
    previous_evidence_root: Path,
    runner: CommandRunner = _default_command_runner,
) -> dict[str, Any]:
    identity = _real_phase_precheck(
        phase="product",
        evidence_root=evidence_root,
        state=state,
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )
    staging = _stage_dir(evidence_root, "product")
    attempt_id = f"product_{uuid.uuid4().hex}"
    try:
        _mark_phase_running(
            evidence_root=evidence_root,
            state=state,
            phase="product",
            attempt_id=attempt_id,
        )
        artifacts = staging / "artifacts"
        command = [
            sys.executable,
            "scripts/smoke_long_novel_provider.py",
            "--provider-file",
            str(provider_file.resolve()),
            "--output-dir",
            str(artifacts),
        ]
        execution = runner(command, ROOT)
        run = _record_execution(
            execution,
            log_path=staging / "provider-run.json",
            redactor=redactor,
            metadata_only=True,
        )
        evidence_path = artifacts / "evidence.json"
        evidence = _read_json(evidence_path) if evidence_path.is_file() else {}
        _assert_product_artifact_boundary(artifacts)
        if execution.returncode == 0:
            passed = _validate_product_artifacts(artifacts, evidence)
        else:
            passed = False
            if artifacts.exists():
                shutil.rmtree(artifacts)
        if _source_tree_hash(evidence_root=evidence_root) != identity["source_tree_sha256"]:
            raise AcceptanceError("source changed during product smoke")
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
        receipt = {
            "schema_version": "final-long-product-smoke-v1",
            "phase": "product",
            "attempt_id": attempt_id,
            "status": "passed" if passed else "failed",
            "created_at": _now(),
            "source_tree_sha256": identity["source_tree_sha256"],
            "head": identity["head"],
            "provider_runtime": _safe_provider(config),
            "execution": run,
            "product_evidence_sha256": (
                _sha256_file(evidence_path) if evidence_path.is_file() else ""
            ),
            "manuscript_sha256": (
                _sha256_file(artifacts / "manuscript.md")
                if (artifacts / "manuscript.md").is_file()
                else ""
            ),
            "manuscript_in_json": False,
        }
        _atomic_json(staging / "receipt.json", receipt)
        _assert_stage_secret_free(staging, evidence_root=evidence_root, redactor=redactor)
        _publish_stage(staging, evidence_root / "product")
        if _source_tree_hash(evidence_root=evidence_root) != identity["source_tree_sha256"]:
            raise AcceptanceError("source changed while publishing product evidence")
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
    except BaseException as exc:
        if staging.exists():
            shutil.rmtree(staging)
        state["phases"]["product"] = {
            "status": "failed",
            "failed_at": _now(),
            "attempt_id": attempt_id,
            "reason": (
                "secret_scan_failed"
                if isinstance(exc, SecretLeakError)
                else "product_execution_failed"
            ),
        }
        _save_state(evidence_root, state)
        raise
    state["phases"]["product"] = {
        "status": receipt["status"],
        "completed_at": _now(),
        "attempt_id": attempt_id,
        "receipt": "product/receipt.json",
        "artifact_tree": _tree_hash(evidence_root / "product"),
    }
    _save_state(evidence_root, state)
    return receipt


def _inventory(root: Path, *, exclude: set[Path] | None = None) -> list[dict[str, Any]]:
    excluded = {item.resolve() for item in (exclude or set())}
    rows = []
    for path in sorted(_artifact_files(root), key=lambda item: item.as_posix()):
        if path.resolve() in excluded:
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return rows


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Final long-novel acceptance",
        "",
        f"Verdict: `{report['verdict']}`",
        "",
        f"- Cycle: `{report['cycle_id']}`",
        f"- Branch: `{report['git']['branch']}`",
        f"- HEAD: `{report['git']['head']}`",
        f"- Source tree: `{report['git']['source_tree_sha256']}`",
        "",
        "## Phases",
        "",
        "| Phase | Status | Receipt |",
        "| --- | --- | --- |",
    ]
    for phase in PHASES:
        item = report["phases"][phase]
        lines.append(
            f"| {phase} | {item.get('status', 'unknown')} | "
            f"{item.get('receipt', '')} |"
        )
    lines.extend(
        [
            "",
            "All Provider and product stages were authorized by the same green "
            "offline source receipt. No credential, endpoint, request header, "
            "prompt, raw response, or narrative prose is embedded in acceptance JSON.",
            "",
        ]
    )
    return "\n".join(lines)


def _recovery_markdown() -> str:
    return "\n".join(
        (
            "# Recovery",
            "",
            "This cycle is immutable and has no resume or force option.",
            "",
            "1. If a phase failed or was interrupted, preserve this evidence root.",
            "2. Fix the source or external condition without modifying protected files.",
            "3. Choose a brand-new evidence root and run `offline` again.",
            "4. Advance only in order: `probe`, `g1`, `g2`, `product`, `final`.",
            "5. Never copy a G1, G2, transaction, or product receipt into a new cycle.",
            "",
        )
    )


def _run_final_phase(
    *,
    evidence_root: Path,
    state: dict[str, Any],
    redactor: ExactRedactor,
    user_root: Path,
    previous_evidence_root: Path,
) -> dict[str, Any]:
    identity = _real_phase_precheck(
        phase="final",
        evidence_root=evidence_root,
        state=state,
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )
    staging = _stage_dir(evidence_root, "final")
    attempt_id = f"final_{uuid.uuid4().hex}"
    published_paths: list[Path] = []
    try:
        _mark_phase_running(
            evidence_root=evidence_root,
            state=state,
            phase="final",
            attempt_id=attempt_id,
        )
        existing_paths = [
            *_source_paths(evidence_root=evidence_root),
            *_artifact_files(evidence_root),
        ]
        exact = scan_exact_secrets(
            existing_paths,
            exact_values=redactor.exact_values,
        )
        generic = scan_generic_secrets(existing_paths)
        if exact["status"] != "passed" or generic["status"] != "passed":
            raise SecretLeakError("final source/evidence secret scan failed")
        for path in _artifact_files(evidence_root):
            if path.suffix.lower() == ".json":
                _metadata_only_json(_read_json(path), location=path.name)
        inventory = _inventory(
            evidence_root,
            exclude={_state_path(evidence_root)},
        )
        manifest = {
            "schema_version": "final-long-novel-manifest-v1",
            "cycle_id": CYCLE_ID,
            "created_at": _now(),
            "artifact_count": len(inventory),
            "artifacts": inventory,
            "product_manuscript": "product/artifacts/manuscript.md",
            "prose_allowed_only_in_product_manuscript": True,
        }
        completed_at = _now()
        final_phase_state = {
            "status": "passed",
            "completed_at": completed_at,
            "attempt_id": attempt_id,
            "receipt": "report.json",
        }
        reported_phases = {
            phase: dict(value) for phase, value in state["phases"].items()
        }
        reported_phases["final"] = final_phase_state
        report = {
            "schema_version": "final-long-novel-report-v1",
            "cycle_id": CYCLE_ID,
            "verdict": "FINAL_LONG_NOVEL_PASS",
            "created_at": completed_at,
            "git": identity,
            "protected": state["protected"],
            "provider_runtime": state["provider_runtime"],
            "phases": reported_phases,
            "final_scans": {"exact": exact, "generic": generic},
            "manifest_artifact_count": len(inventory),
            "secret_values_persisted": False,
            "raw_response_persisted": False,
            "prose_in_evidence_json": False,
        }
        _metadata_only_json(manifest)
        _metadata_only_json(report)
        _atomic_json(staging / "manifest.json", manifest)
        _atomic_json(staging / "report.json", report)
        _atomic_text(staging / "report.md", _report_markdown(report))
        _atomic_text(staging / "recovery.md", _recovery_markdown())
        hashes = {
            row["path"]: {"sha256": row["sha256"], "bytes": row["bytes"]}
            for row in inventory
        }
        for name in ("manifest.json", "report.json", "report.md", "recovery.md"):
            path = staging / name
            hashes[name] = {
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
        _atomic_json(
            staging / "artifact-sha256.json",
            {
                "schema_version": "final-long-novel-artifact-sha256-v1",
                "artifacts": hashes,
            },
        )
        combined = [
            *_source_paths(evidence_root=evidence_root),
            *_artifact_files(evidence_root),
            *_artifact_files(staging),
        ]
        exact_after = scan_exact_secrets(
            combined,
            exact_values=redactor.exact_values,
        )
        generic_after = scan_generic_secrets(combined)
        if exact_after["status"] != "passed" or generic_after["status"] != "passed":
            raise SecretLeakError("final staged report failed secret scan")
        for name in FINAL_FILENAMES:
            target = evidence_root / name
            if target.exists():
                raise AcceptanceError(f"final artifact already exists: {name}")
            os.replace(staging / name, target)
            published_paths.append(target)
        staging.rmdir()
        final_scan_paths = [
            *_source_paths(evidence_root=evidence_root),
            *_artifact_files(evidence_root),
        ]
        if (
            scan_exact_secrets(
                final_scan_paths,
                exact_values=redactor.exact_values,
            )["status"]
            != "passed"
            or scan_generic_secrets(final_scan_paths)["status"] != "passed"
        ):
            raise SecretLeakError("published final artifacts failed verification")
        _verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
        )
        if _source_tree_hash(evidence_root=evidence_root) != identity["source_tree_sha256"]:
            raise AcceptanceError("source changed during finalization")
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        for path in published_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        state["phases"]["final"] = {
            "status": "failed",
            "failed_at": _now(),
            "reason": "finalization_failed",
        }
        _save_state(evidence_root, state)
        raise
    state["phases"]["final"] = final_phase_state
    state["final_artifacts"] = {
        name: _sha256_file(evidence_root / name) for name in FINAL_FILENAMES
    }
    _save_state(evidence_root, state)
    return report


def _is_actionable_secret_finding(
    finding: dict[str, str], changed_values: set[str]
) -> bool:
    """Compatibility helper retained for callers of the superseded runner."""

    return finding.get("scope") == "artifact" or finding.get("path", "") in changed_values


def _overall_verdict(
    gates: dict[str, dict[str, Any]],
    *,
    offline_status: str,
    secret_status: str,
    human_review_status: str = "not_started",
) -> str:
    """Compatibility-only verdict calculation for historical unit tests."""

    if offline_status != "passed" or secret_status != "passed":
        return "NOVEL_AUTO_FINAL_FAIL"
    if any(item.get("status") == "failed" for item in gates.values()):
        return "NOVEL_AUTO_FINAL_FAIL"
    if any(item.get("status") == "blocked" for item in gates.values()):
        return "NOVEL_AUTO_FINAL_BLOCKED"
    if all(gates.get(f"P{index}", {}).get("status") == "passed" for index in range(9)):
        return (
            "NOVEL_AUTO_FINAL_PASS"
            if human_review_status == "passed"
            else "NOVEL_AUTO_FINAL_CANDIDATE"
        )
    return "NOVEL_AUTO_FINAL_FAIL"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--provider-file", type=Path, required=True)
    parser.add_argument("--user-root", type=Path, required=True)
    parser.add_argument("--previous-evidence-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    return parser


def run_phase(
    args: argparse.Namespace,
    *,
    runner: CommandRunner = _default_command_runner,
) -> dict[str, Any]:
    evidence_root = args.evidence_root.expanduser().resolve()
    user_root = args.user_root.expanduser().resolve()
    previous_evidence_root = args.previous_evidence_root.expanduser().resolve()
    provider_file = args.provider_file.expanduser().resolve()
    _assert_provider_binding(provider_file=provider_file, user_root=user_root)
    config = _load_provider(provider_file)
    redactor = ExactRedactor(api_key=config.api_key, base_url=config.base_url)
    if args.phase == "offline":
        state = _initialize_cycle(
            evidence_root=evidence_root,
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
            provider_file=provider_file,
            config=config,
        )
        return _run_offline_phase(
            evidence_root=evidence_root,
            state=state,
            redactor=redactor,
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
            runner=runner,
        )
    state = _load_cycle(
        evidence_root=evidence_root,
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )
    _assert_provider_binding(
        provider_file=provider_file,
        user_root=user_root,
        config=config,
        state=state,
    )
    if args.phase == "probe":
        return _run_probe_phase(
            evidence_root=evidence_root,
            state=state,
            redactor=redactor,
            config=config,
            provider_file=provider_file,
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
            runner=runner,
        )
    if args.phase in {"g1", "g2"}:
        return _run_matrix_phase(
            phase=args.phase,
            evidence_root=evidence_root,
            state=state,
            redactor=redactor,
            config=config,
            provider_file=provider_file,
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
            runner=runner,
        )
    if args.phase == "product":
        return _run_product_phase(
            evidence_root=evidence_root,
            state=state,
            redactor=redactor,
            config=config,
            provider_file=provider_file,
            user_root=user_root,
            previous_evidence_root=previous_evidence_root,
            runner=runner,
        )
    return _run_final_phase(
        evidence_root=evidence_root,
        state=state,
        redactor=redactor,
        user_root=user_root,
        previous_evidence_root=previous_evidence_root,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_phase(args)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": "acceptance phase failed closed",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "passed" or result.get("verdict") == "FINAL_LONG_NOVEL_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
