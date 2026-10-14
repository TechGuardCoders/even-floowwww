# Even Floowwww

Live traffic record & replay. Record real request/response traffic to an
append-only JSONL file, then replay it later against a candidate backend at
the original rate — or scaled up/down — to see how it behaves before it
takes production load.

## Why

Staging never looks like production. The requests are wrong, the timing is
wrong, and the failures you care about never show up. Even Floowwww fixes
that by capturing the real thing: actual requests, actual responses, actual
inter-request timing — and replaying it faithfully.

## Architecture

```
 live traffic ──▶ Recorder.append(entry) ──▶ traffic.jsonl (append-only,
                                              timestamped, one JSON per line)

 traffic.jsonl ──▶ Replayer.load(path) ──▶ Replayer.run(target_fn,
                                            rate_scale=1.0) ──▶ results
```

- **Recorder** — appends timestamped entries (`id`, `timestamp`, `request`,
  `response`) to a JSONL file. Monotonic ids survive process restarts.
- **Replayer** — loads the file and replays entries against an injectable
  `target_fn`, preserving original inter-entry gaps divided by `rate_scale`.
  Returns per-entry latency, status, and any error (errors never crash the
  replay).

## Results

`Replayer.run` returns a list of `ReplayResult`:

```python
ReplayResult(entry_id=1, status=200, latency=0.0031, error=None)
```

## Usage

Record:

```python
from even_floowwww import Recorder

rec = Recorder("traffic.jsonl")
rec.append({"method": "GET", "path": "/api/items"}, {"status": 200})
```

Replay at 2x speed against any callable:

```python
from even_floowwww import Replayer

rp = Replayer.load("traffic.jsonl")
results = rp.run(my_target_fn, rate_scale=2.0)
failed = [r for r in results if r.error or (r.status or 0) >= 500]
```

`target_fn` is injectable — pass anything that takes a request dict and
returns an object with a `status` attribute (or an int). No live network is
required, which keeps tests hermetic.

## Notes

- Pure Python stdlib; no dependencies.
- `rate_scale` must be > 0 (1.0 = original timing, 2.0 = twice as fast).
- This project is a standalone tool; it does not proxy or touch any running
  service. Read-only observability endpoints only, by design.

## License

MIT
