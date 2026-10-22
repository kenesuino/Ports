"""Regression tests for the rail, header, panel, and preferences changes."""

from __future__ import annotations

import pytest

from ports import config_store
from ports.port_monitor import Listener, OwnerIdentity
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.workspace_navigation import derive_rows


def listener(port: int, pid: int = 100, name: str = "node.exe",
             env: str = "windows", distro: str = "") -> Listener:
    owner = OwnerIdentity(env, pid, 1.0, name, distro) if pid else None
    return Listener("127.0.0.1", port, owner, env, distro)


# -- workspace panel derivation ------------------------------------------

class FakeSession:
    def __init__(self, definition_id, name, state="ready", profile_id="p1"):
        self.definition_id = definition_id
        self.name = name
        self.state = state
        self.profile_id = profile_id
        self.listeners = []
        self.shell = "cmd"


def test_panel_lists_running_and_stopped_in_profile_order():
    first = TerminalProfile(name="Frontend")
    second = TerminalProfile(name="API")
    profile = WorkspaceProfile(id="p1", name="dev", terminals=[first, second])
    sessions = [FakeSession(first.id, "Frontend", "running")]
    rows = derive_rows(profile, sessions)
    assert [row["state"] for row in rows] == ["running", "stopped"]
    assert rows[1]["session"] is None
    assert rows[1]["definition"] is second


def test_panel_reports_failed_state():
    terminal = TerminalProfile(name="Broken")
    profile = WorkspaceProfile(id="p1", name="dev", terminals=[terminal])
    rows = derive_rows(profile, [FakeSession(terminal.id, "Broken", "failed")])
    assert rows[0]["state"] == "failed"


def test_panel_includes_session_without_definition():
    profile = WorkspaceProfile(id="p1", name="dev",
                               terminals=[TerminalProfile(name="Known")])
    orphan = FakeSession("unknown-id", "Ad-hoc")
    rows = derive_rows(profile, [orphan])
    assert any(row["session"] is orphan for row in rows)


def test_panel_without_profile_lists_sessions():
    rows = derive_rows(None, [FakeSession("x", "Loose")])
    assert len(rows) == 1 and rows[0]["definition"] is None


# -- config additions ----------------------------------------------------

def test_new_settings_default_and_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config = config_store.load()
    assert config.external_group_open is False
    assert config.workspace_panel_visible is True
    assert config.restore_layout is True
    config.external_group_open = True
    config.workspace_panel_width = 300
    config.probe_interval = 12
    assert config_store.save(config)
    loaded = config_store.load()
    assert loaded.external_group_open is True
    assert loaded.workspace_panel_width == 300
    assert loaded.probe_interval == 12


def test_panel_width_and_probe_interval_are_clamped(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import json
    path = tmp_path / "Ports" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "version": 2,
        "workspace_panel_width": 5000,
        "probe_interval": 1,
        "scrollback_lines": 10000,
    }), encoding="utf-8")
    config = config_store.load()
    assert config.workspace_panel_width == 420
    assert config.probe_interval == 2


# -- merged ports list ---------------------------------------------------

def test_external_rows_use_the_same_row_type():
    from ports.sidebar import PortRow, PortsList
    ports_list = PortsList()
    session = FakeSession("d1", "Web")
    session.id = "s1"
    session.listeners = [listener(3000)]
    ports_list.update_rows([session], {}, external=[listener(9000, 200)], external_open=True)
    kinds = {key[0] for key in ports_list._rows}
    assert kinds == {"session", "external"}
    assert all(isinstance(row, PortRow) for row in ports_list._rows.values())


def test_external_group_collapses_rows_without_rebuilding():
    from ports.sidebar import PortsList
    ports_list = PortsList()
    ports_list.update_rows([], {}, external=[listener(9000, 200)],
                           external_open=False)
    external_rows = [row for key, row in ports_list._rows.items()
                     if key[0] == "external"]
    # isHidden reflects the row's own flag; isVisible would also be false just
    # because the list itself was never shown.
    assert external_rows and external_rows[0].isHidden()
    ports_list.set_external_open(True)
    assert not external_rows[0].isHidden()


def test_port_row_does_not_use_a_cursor_tooltip():
    from ports.sidebar import PortRow
    row = PortRow(listener(3000))
    assert row.toolTip() == ""
    assert "PID 100" in row.accessibleDescription()


def test_port_row_hover_detail_includes_address_and_pid():
    from ports.sidebar import PortRow
    row = PortRow(listener(5173, 4242, "node.exe"))
    detail = row._detail_text()
    assert "127.0.0.1:5173" in detail
    assert "PID 4242" in detail


# -- preferences ---------------------------------------------------------

def test_preferences_rejects_invalid_filter_entry():
    from ports.preferences import PreferencesDialog
    dialog = PreferencesDialog(config_store.Config())
    dialog.denylist.setPlainText("ok.exe")
    assert dialog._parse_list(dialog.denylist, "denylist") == ["ok.exe"]
    with pytest.raises(ValueError):
        dialog.denylist.setPlainText("bad$(whoami).exe")
        dialog._parse_list(dialog.denylist, "denylist")


def test_preferences_has_all_sections():
    from ports.preferences import PreferencesDialog, SECTIONS
    dialog = PreferencesDialog(config_store.Config())
    assert dialog.sections.count() == len(SECTIONS)
    assert dialog.pages.count() == len(SECTIONS)
