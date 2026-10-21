import json
from unittest.mock import patch
from ports.config_store import Config, load, save, recover


def test_v1_migration_retains_legacy_labels_and_commands(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    target = tmp_path / 'Ports' / 'config.json'
    target.parent.mkdir()
    target.write_text(json.dumps({'version': 1, 'port_labels': {'old:3000': 'api'},
                                 'saved_sessions': [{'name': 'api', 'shell': 'cmd', 'cwd': '', 'startup_cmd': 'echo hi'}]}))
    config = load()
    assert config.port_labels['old:3000'] == 'api'
    identity = config.saved_sessions[0].id
    assert save(config)
    assert load().saved_sessions[0].id == identity
    assert load().saved_sessions[0].startup_cmd == 'echo hi'


def test_failed_replace_preserves_prior_config(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    config = Config()
    assert save(config)
    target = tmp_path / 'Ports' / 'config.json'
    original = target.read_bytes()
    config.view_mode = 'tabs'
    with patch('ports.config_store.os.replace', side_effect=OSError('blocked')):
        assert not save(config)
    assert target.read_bytes() == original
    assert 'blocked' in config.last_error


def test_explicit_recovery_backs_up_original(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    target = tmp_path / 'Ports' / 'config.json'
    target.parent.mkdir()
    target.write_text('{bad')
    config = load()
    assert config.read_only and not save(config)
    assert recover(config)
    assert save(config)
    backups = list(target.parent.glob('*.recovery-*.json'))
    assert backups and backups[0].read_text() == '{bad'
