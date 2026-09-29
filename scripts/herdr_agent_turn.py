#!/usr/bin/env python3
"""Submit one Herdr agent turn, wait once, and emit compact result metadata."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


MAX_PROMPT_BYTES = 64 * 1024
DEFAULT_MAX_HANDOFF_BYTES = 12 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, help="Unique Herdr agent name or pane ID")
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt", help="Bounded worker prompt")
    prompt.add_argument("--prompt-file", type=Path, help="UTF-8 file containing the prompt")
    parser.add_argument("--handoff-path", type=Path, help="Unused path for the compact handoff")
    parser.add_argument("--timeout-ms", type=int, help="Optional Herdr timeout; omitted means wait indefinitely")
    parser.add_argument("--read-lines", type=int, default=80)
    parser.add_argument("--max-handoff-bytes", type=int, default=DEFAULT_MAX_HANDOFF_BYTES)
    return parser.parse_args()


def fail(message: str, code: int = 2) -> int:
    print(json.dumps({"outcome": "invalid_request", "message": message}))
    return code


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def load_json(text: str) -> dict:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def agent_status(payload: dict) -> str | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    agent = result.get("agent")
    if not isinstance(agent, dict):
        return None
    status = agent.get("agent_status") or agent.get("status")
    return status if isinstance(status, str) else None


def main() -> int:
    args = parse_args()
    if os.environ.get("HERDR_ENV") != "1":
        return fail("HERDR_ENV=1 is required; run the owner inside Herdr")
    if args.timeout_ms is not None and args.timeout_ms <= 0:
        return fail("--timeout-ms must be positive")
    if args.read_lines <= 0 or args.max_handoff_bytes <= 0:
        return fail("--read-lines and --max-handoff-bytes must be positive")

    herdr = os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr")
    if not herdr:
        return fail("herdr is not available in PATH and HERDR_BIN_PATH is unset", 127)
    if not Path(herdr).is_file() or not os.access(herdr, os.X_OK):
        return fail("resolved Herdr binary is not an executable file", 127)

    try:
        prompt = args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else args.prompt
    except (OSError, UnicodeError) as error:
        return fail(f"cannot read prompt: {error}")
    assert prompt is not None
    if "\0" in prompt:
        return fail("prompt contains a NUL byte")
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        return fail(f"prompt exceeds {MAX_PROMPT_BYTES} bytes")

    if args.handoff_path:
        handoff_path = args.handoff_path.expanduser().resolve()
        if handoff_path.exists():
            return fail("--handoff-path must not already exist")
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir = Path(tempfile.mkdtemp(prefix="herdr-turn-"))
    os.chmod(artifact_dir, 0o700)
    if not args.handoff_path:
        handoff_path = artifact_dir / "handoff.md"
    transcript_path = artifact_dir / "terminal.txt"
    diagnostic_path = artifact_dir / "herdr-diagnostic.json"

    contract = (
        "\n\nBefore finishing, write a compact Markdown handoff to this exact path: "
        f"{handoff_path}\n"
        "Include: status, task, base_head, result, files_changed, verification "
        "with exact commands and PASS/FAIL/NOT RUN, risks, and next_decision. "
        f"Keep it under {args.max_handoff_bytes} bytes. Put detailed evidence in "
        "separate files. Your final terminal message should contain only the handoff path."
    )
    command = [herdr, "agent", "prompt", args.agent, prompt.rstrip() + contract, "--wait"]
    if args.timeout_ms is not None:
        command.extend(["--timeout", str(args.timeout_ms)])

    waited = run(command)
    prompt_payload = load_json(waited.stdout)

    inspected = run([herdr, "agent", "get", args.agent])
    inspect_payload = load_json(inspected.stdout)
    status = agent_status(inspect_payload) or agent_status(prompt_payload) or "unknown"

    read = run(
        [
            herdr,
            "agent",
            "read",
            args.agent,
            "--source",
            "recent-unwrapped",
            "--lines",
            str(args.read_lines),
        ]
    )
    transcript_path.write_text(read.stdout, encoding="utf-8")
    os.chmod(transcript_path, 0o600)

    diagnostic = {
        "prompt_returncode": waited.returncode,
        "prompt_stdout": prompt_payload or None,
        "prompt_stderr": load_json(waited.stderr) or waited.stderr[-1000:] or None,
        "inspect_returncode": inspected.returncode,
        "inspect_stdout": inspect_payload or None,
        "inspect_stderr": load_json(inspected.stderr) or inspected.stderr[-1000:] or None,
        "read_returncode": read.returncode,
        "read_stderr": load_json(read.stderr) or read.stderr[-1000:] or None,
    }
    diagnostic_path.write_text(json.dumps(diagnostic, indent=2) + "\n", encoding="utf-8")
    os.chmod(diagnostic_path, 0o600)

    unsafe_handoff = handoff_path.is_symlink()
    valid_handoff = handoff_path.is_file() and not unsafe_handoff
    handoff_bytes = handoff_path.stat().st_size if valid_handoff else 0
    if valid_handoff:
        os.chmod(handoff_path, 0o600)

    if unsafe_handoff:
        outcome, exit_code = "unsafe_handoff", 23
    elif waited.returncode != 0:
        outcome, exit_code = "herdr_error", 10
    elif status == "blocked":
        outcome, exit_code = "blocked", 0
    elif status not in {"done", "idle"}:
        outcome, exit_code = "inconclusive", 22
    elif not valid_handoff:
        outcome, exit_code = "missing_handoff", 20
    elif handoff_bytes > args.max_handoff_bytes:
        outcome, exit_code = "handoff_too_large", 21
    else:
        outcome, exit_code = "handoff_ready", 0

    print(
        json.dumps(
            {
                "outcome": outcome,
                "agent": args.agent,
                "agent_status": status,
                "handoff_path": str(handoff_path),
                "handoff_bytes": handoff_bytes,
                "terminal_path": str(transcript_path),
                "diagnostic_path": str(diagnostic_path),
                "herdr_returncode": waited.returncode,
            },
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
