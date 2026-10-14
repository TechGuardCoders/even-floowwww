"""Even Floowwww — record real traffic to JSONL, replay it later.

Recorder.append(entry) appends timestamped request/response entries to a
JSONL file. Replayer.load(path) reads them back and Replayer.run(target_fn,
rate_scale=1.0) replays them against an injectable target function,
preserving original inter-entry timing (scaled by rate_scale).

Pure Python stdlib. No live network in CI: target_fn is injectable.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

__all__ = ["Recorder", "Replayer", "ReplayResult"]


@dataclass
class ReplayResult:
    """Outcome of replaying a single recorded entry."""

    entry_id: int
    status: Optional[int]
    latency: float
    error: Optional[str] = None


class Recorder:
    """Append-only JSONL recorder for request/response traffic."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Append one entry; returns the entry as written."""
        entry = {
            "id": self._next_id(),
            "timestamp": timestamp if timestamp is not None else time.time(),
            "request": request,
            "response": response,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def _next_id(self) -> int:
        """Monotonic id: last line's id + 1 (0 for a fresh file)."""
        last = 0
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            last = int(json.loads(line).get("id", last))
                        except (json.JSONDecodeError, ValueError):
                            continue
        return last + 1


class Replayer:
    """Replay recorded traffic against an injectable target function."""

    def __init__(self, entries: List[Dict[str, Any]]):
        self.entries = entries

    @classmethod
    def load(cls, path: str | Path) -> "Replayer":
        entries: List[Dict[str, Any]] = []
        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return cls(entries)

    def run(
        self,
        target_fn: Callable[[Dict[str, Any]], Any],
        rate_scale: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> List[ReplayResult]:
        """Replay entries preserving original inter-entry gaps / rate_scale.

        target_fn receives the entry's request dict and must return an object
        with a ``status`` attribute (or an int status). Returns per-entry
        latency and status; errors are captured, never raised.
        """
        if rate_scale <= 0:
            raise ValueError("rate_scale must be > 0")
        results: List[ReplayResult] = []
        prev_ts: Optional[float] = None
        for entry in self.entries:
            ts = float(entry.get("timestamp", 0.0))
            if prev_ts is not None:
                gap = max(0.0, (ts - prev_ts)) / rate_scale
                if gap > 0:
                    sleep(gap)
            prev_ts = ts
            start = clock()
            error: Optional[str] = None
            status: Optional[int] = None
            try:
                resp = target_fn(entry.get("request", {}))
                status = resp if isinstance(resp, int) else getattr(resp, "status", None)
            except Exception as exc:  # noqa: BLE001 - replay must not crash
                error = f"{type(exc).__name__}: {exc}"
            results.append(
                ReplayResult(
                    entry_id=int(entry.get("id", 0)),
                    status=status,
                    latency=clock() - start,
                    error=error,
                )
            )
        return results
