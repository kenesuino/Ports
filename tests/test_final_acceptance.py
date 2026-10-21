"""Final source review checklist, independently runnable without terminal UI."""
from pathlib import Path
from ports.profiles import TerminalProfile, WorkspaceProfile


def test_invalid_profile_ports_and_duplicate_ids():
    import pytest
    terminal = TerminalProfile().to_dict()
    terminal['expected_ports'] = [0]
    with pytest.raises(ValueError):
        TerminalProfile.from_dict(terminal)
    profile = WorkspaceProfile(terminals=[TerminalProfile()]).to_dict()
    profile['terminals'].append(dict(profile['terminals'][0]))
    with pytest.raises(ValueError):
        WorkspaceProfile.from_dict(profile)


def test_protocol_reply_does_not_cancel_startup():
    from ports.session_manager import TerminalSession
    from unittest.mock import Mock
    session = TerminalSession('test', 'powershell', '', 'echo hello')
    session.pty = Mock()
    session._on_input('\x1b[1;1R')
    assert session._startup_pending
    session._on_prompt('C:/work')
    session.pty.write.assert_called_with('echo hello\r')


def test_supplied_icon_preserved():
    source = Path(r'D:\Downloads\localhost-port-reference-vector.svg')
    if source.exists():
        assert source.read_bytes().replace(b'\r\n', b'\n') == Path('ports/assets/ports.svg').read_bytes().replace(b'\r\n', b'\n')
