"""Cross-platform per-run lock shared by provider adapters."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
import threading

_registry_guard = threading.Lock()
_thread_locks: dict[str, threading.RLock] = {}


@contextmanager
def run_lock(run_dir: Path):
    """Serialize budget check + provider operation + ledger write for a run."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_key = str((run_dir / ".provider-budget.lock").resolve())
    with _registry_guard:
        thread_lock = _thread_locks.setdefault(lock_key, threading.RLock())
    thread_lock.acquire()
    handle = None
    file_locked = False
    try:
        handle = (run_dir / ".provider-budget.lock").open("a+b")
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            file_locked = True
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            file_locked = True
        yield
    finally:
        try:
            if handle is not None:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    if file_locked:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    if file_locked:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
        finally:
            thread_lock.release()
