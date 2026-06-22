import pytest

from scripts import import_feishu_messages


def test_parse_args_defaults_to_one_shot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["import_feishu_messages.py"])

    args = import_feishu_messages.parse_args()

    assert args.watch is False
    assert args.once is False
    assert args.interval > 0


def test_parse_args_accepts_watch_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["import_feishu_messages.py", "--watch", "--interval", "2.5"])

    args = import_feishu_messages.parse_args()

    assert args.watch is True
    assert args.interval == 2.5


def test_watch_processes_then_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    processed = []

    def fake_process_once() -> int:
        processed.append("processed")
        return 0

    def fake_sleep(interval: float) -> None:
        assert interval == 2
        raise KeyboardInterrupt

    monkeypatch.setattr(import_feishu_messages, "process_once", fake_process_once)
    monkeypatch.setattr(import_feishu_messages.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        import_feishu_messages.watch(2)

    assert processed == ["processed"]


def test_process_once_prints_stats(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class FakeService:
        def __init__(self, repository) -> None:
            self.repository = repository

        async def import_configured_chats(self):
            return _Stats()

    class FakeRepository:
        def __init__(self, session) -> None:
            self.session = session

        def ensure_seed_data(self) -> None:
            pass

    monkeypatch.setattr(import_feishu_messages, "SessionLocal", _fake_session_local)
    monkeypatch.setattr(import_feishu_messages, "PostsRepository", FakeRepository)
    monkeypatch.setattr(import_feishu_messages, "FeishuRequirementImportService", FakeService)

    assert import_feishu_messages.process_once() == 6
    output = capsys.readouterr().out
    assert "fetched=6" in output
    assert "created=1" in output
    assert "failed=1" in output


class _Stats:
    fetched = 6
    skipped = 1
    created = 1
    voted = 2
    already_voted = 1
    failed = 1


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        pass


def _fake_session_local() -> _FakeSession:
    return _FakeSession()
