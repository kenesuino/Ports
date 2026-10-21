import pytest

from ports.config_store import Config, SavedSession, load, save


def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = Config()
    cfg.set_label("pwsh", 3000, "frontend")
    cfg.saved_sessions = [SavedSession("api", "pwsh", "F:/x", "npm run dev")]
    cfg.scrollback_lines = 5000
    assert save(cfg)

    loaded = load()
    assert loaded.get_label("pwsh", 3000) == "frontend"
    assert loaded.saved_sessions[0].startup_cmd == "npm run dev"
    assert loaded.scrollback_lines == 5000


def test_missing_file_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "nope"))
    cfg = load()
    assert cfg.port_labels == {}
    assert "svchost.exe" in cfg.process_denylist


def test_corrupt_json_defaults_and_file_retained(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = tmp_path / "Ports" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    cfg = load()
    assert cfg.port_labels == {}
    assert path.read_text(encoding="utf-8") == "{not json"  # not overwritten


def test_wrong_version_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = tmp_path / "Ports" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"version": 99, "port_labels": {"a": "b"}}', encoding="utf-8")
    assert load().port_labels == {}


def test_bad_session_entries_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = tmp_path / "Ports" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"version": 1, "saved_sessions": [42, {"shell": "evil", "name": "ok"}]}',
        encoding="utf-8",
    )
    sessions = load().saved_sessions
    assert len(sessions) == 1
    assert sessions[0].shell == "pwsh"  # invalid shell coerced


def test_label_clear_removes_key():
    cfg = Config()
    cfg.set_label("cmd", 80, "x")
    cfg.set_label("cmd", 80, "   ")
    assert cfg.get_label("cmd", 80) == ""
