"""Config navigation migration keeps unpinned lists empty across reloads."""
import json
from ports.config_store import Config, load, save
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.workspace_navigation import OTHER


def test_first_upgrade_loads_profiles_once_then_respects_empty(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    profile = WorkspaceProfile(name='dev', terminals=[TerminalProfile()])
    path = tmp_path / 'Ports/config.json'; path.parent.mkdir()
    path.write_text(json.dumps({'version': 2, 'profiles': [profile.to_dict()], 'rail_collapsed': True, 'workspace_panel_width': 310}))
    config = load()
    assert config.loaded_workspace_ids == [profile.id]
    assert not config.rail_collapsed
    assert config.ports_inspector_width == 310
    config.loaded_workspace_ids = []
    assert save(config)
    assert load().loaded_workspace_ids == []


def test_missing_profiles_pruned_with_notice_and_bad_types_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    path = tmp_path / 'Ports/config.json'; path.parent.mkdir()
    path.write_text(json.dumps({'version': 2, 'loaded_workspace_ids': ['gone']}))
    config = load()
    assert config.loaded_workspace_ids == [] and config.warning
    path.write_text(json.dumps({'version': 2, 'loaded_workspace_ids': 99}))
    original = path.read_bytes()
    config = load()
    assert config.read_only and not save(config)
    assert path.read_bytes() == original
