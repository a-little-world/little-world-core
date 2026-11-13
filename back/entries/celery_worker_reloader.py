"""Restart the Celery worker when backend Python sources change (dev only)."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

IGNORE_DIR_NAMES = frozenset({"__pycache__", ".git", ".venv", "venv", "node_modules"})


def collect_py_mtimes(root: str) -> dict[str, float]:
    mtimes: dict[str, float] = {}
    root_path = Path(root)
    if not root_path.exists():
        return mtimes
    for path in root_path.rglob("*.py"):
        if any(part in IGNORE_DIR_NAMES for part in path.parts):
            continue
        try:
            mtimes[str(path)] = path.stat().st_mtime
        except OSError:
            continue
    return mtimes


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            process.kill()
        process.wait(timeout=5)


def start_celery() -> subprocess.Popen:
    command = ["celery", "-A", "back", "worker", "--loglevel=info"]
    print(f"[celery_worker_reloader] starting: {' '.join(command)}", flush=True)
    return subprocess.Popen(command, start_new_session=True)


def main() -> None:
    backend_watch_root = os.getenv("CELERY_WATCH_ROOT", "/back").strip() or "/back"
    debounce_seconds = float(os.getenv("CELERY_RELOAD_DEBOUNCE", "2"))
    poll_interval = float(os.getenv("CELERY_RELOAD_POLL_INTERVAL", "1"))

    last_py_mtimes = collect_py_mtimes(backend_watch_root)
    celery_process = start_celery()
    restart_pending_since: float | None = None

    try:
        while True:
            time.sleep(poll_interval)

            current_py_mtimes = collect_py_mtimes(backend_watch_root)
            if current_py_mtimes != last_py_mtimes:
                last_py_mtimes = current_py_mtimes
                restart_pending_since = time.monotonic()
                print(
                    f"[celery_worker_reloader] source change detected; debouncing {debounce_seconds:.1f}s...",
                    flush=True,
                )

            if restart_pending_since is not None and (time.monotonic() - restart_pending_since) >= debounce_seconds:
                print("[celery_worker_reloader] restarting Celery worker", flush=True)
                stop_process(celery_process)
                celery_process = start_celery()
                restart_pending_since = None
                last_py_mtimes = collect_py_mtimes(backend_watch_root)

            if celery_process.poll() is not None:
                print(
                    f"[celery_worker_reloader] Celery exited with {celery_process.returncode}; restarting",
                    flush=True,
                )
                celery_process = start_celery()
    except KeyboardInterrupt:
        stop_process(celery_process)


if __name__ == "__main__":
    main()
