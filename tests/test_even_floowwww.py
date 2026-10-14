import json
import time

import pytest

from even_floowwww import Recorder, Replayer


class FakeResponse:
    def __init__(self, status):
        self.status = status


def test_recorder_appends_jsonl(tmp_path):
    path = tmp_path / "traffic.jsonl"
    rec = Recorder(path)
    e1 = rec.append({"method": "GET", "path": "/a"}, {"status": 200})
    e2 = rec.append({"method": "POST", "path": "/b"}, {"status": 201})
    assert e1["id"] == 1 and e2["id"] == 2
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["request"]["path"] == "/a"


def test_recorder_ids_resume_across_instances(tmp_path):
    path = tmp_path / "traffic.jsonl"
    Recorder(path).append({"m": "GET"}, {"status": 200})
    rec2 = Recorder(path)
    entry = rec2.append({"m": "GET"}, {"status": 200})
    assert entry["id"] == 2


def test_recorder_skips_corrupt_lines(tmp_path):
    path = tmp_path / "traffic.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    rec = Recorder(path)
    assert rec.append({}, {}).get("id") == 1


def test_replayer_load_roundtrip(tmp_path):
    path = tmp_path / "traffic.jsonl"
    rec = Recorder(path)
    rec.append({"p": 1}, {"status": 200}, timestamp=100.0)
    rec.append({"p": 2}, {"status": 404}, timestamp=100.5)
    rp = Replayer.load(path)
    assert len(rp.entries) == 2
    assert rp.entries[1]["response"]["status"] == 404


def test_replayer_run_reports_latency_and_status():
    def target(request):
        return FakeResponse(200)

    rp = Replayer(
        [
            {"id": 1, "timestamp": 1.0, "request": {"a": 1}, "response": {}},
            {"id": 2, "timestamp": 1.0, "request": {"a": 2}, "response": {}},
        ]
    )
    results = rp.run(target, rate_scale=1.0, clock=time.monotonic, sleep=lambda s: None)
    assert [r.status for r in results] == [200, 200]
    assert all(r.latency >= 0 for r in results)
    assert [r.entry_id for r in results] == [1, 2]


def test_replayer_preserves_timing_scaled():
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)

    rp = Replayer(
        [
            {"id": 1, "timestamp": 10.0, "request": {}, "response": {}},
            {"id": 2, "timestamp": 11.0, "request": {}, "response": {}},
            {"id": 3, "timestamp": 13.0, "request": {}, "response": {}},
        ]
    )
    rp.run(lambda r: FakeResponse(200), rate_scale=2.0, sleep=fake_sleep)
    assert slept == [0.5, 1.0]


def test_replayer_rate_scale_zero_raises():
    rp = Replayer([{"id": 1, "timestamp": 0, "request": {}, "response": {}}])
    with pytest.raises(ValueError):
        rp.run(lambda r: None, rate_scale=0.0)


def test_replayer_captures_errors():
    def boom(request):
        raise RuntimeError("down")

    rp = Replayer([{"id": 1, "timestamp": 0, "request": {}, "response": {}}])
    results = rp.run(boom, sleep=lambda s: None)
    assert results[0].error is not None
    assert "RuntimeError" in results[0].error
    assert results[0].status is None


def test_replayer_accepts_int_status():
    rp = Replayer([{"id": 1, "timestamp": 0, "request": {}, "response": {}}])
    results = rp.run(lambda r: 204, sleep=lambda s: None)
    assert results[0].status == 204
