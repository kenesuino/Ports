from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.config_store import Config, load, save


def test_approval_fingerprint_only_execution_changes():
    terminal = TerminalProfile(name="api")
    profile = WorkspaceProfile(terminals=[terminal])
    profile.approve()
    terminal.name = "renamed"
    terminal.accent = "#9ece6a"
    assert not profile.needs_review()
    terminal.startup_cmd = "python server.py"
    assert profile.needs_review()


def test_roundtrip_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    profile = WorkspaceProfile(name="dev", terminals=[TerminalProfile()])
    profile.approve()
    config = Config(profiles=[profile])
    assert save(config)
    loaded = load()
    assert loaded.profiles[0].id == profile.id
    assert not loaded.profiles[0].needs_review()


def test_corrupt_config_refuses_save(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = tmp_path / "Ports" / "config.json"
    path.parent.mkdir()
    path.write_text("{broken")
    config = load()
    assert config.read_only
    assert not save(config)
    assert path.read_text() == "{broken"
