import pytest

from scripts import process_notifications


def test_parse_args_defaults_to_one_shot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["process_notifications.py"])

    args = process_notifications.parse_args()

    assert args.watch is False
    assert args.interval == 3.0


def test_parse_args_accepts_watch_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["process_notifications.py", "--watch", "--interval", "1.5"])

    args = process_notifications.parse_args()

    assert args.watch is True
    assert args.interval == 1.5


def test_watch_processes_then_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    processed = []

    def fake_process_once() -> int:
        processed.append("processed")
        return 0

    def fake_sleep(interval: float) -> None:
        assert interval == 3
        raise KeyboardInterrupt

    monkeypatch.setattr(process_notifications, "process_once", fake_process_once)
    monkeypatch.setattr(process_notifications.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        process_notifications.watch(3)

    assert processed == ["processed"]
