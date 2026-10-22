from types import SimpleNamespace as S
from ports.workspace_navigation import WorkspaceNavigation, OTHER, format_duration, SessionAge


def test_unpin_reload_and_subset_order():
    nav = WorkspaceNavigation(['a', 'b'], 'a')
    sessions = [S(id='a1', profile_id='a'), S(id='b1', profile_id='b'), S(id='a2', profile_id='a')]
    assert [s.id for s in nav.visible(sessions)] == ['a1', 'a2']
    assert nav.reordered(sessions, ['a2', 'a1']) == ['a2', 'b1', 'a1']
    nav.unpin('a')
    assert nav.selected == OTHER
    assert [s.id for s in nav.visible(sessions)] == ['a1', 'a2']
    nav.load('a'); nav.load('a')
    assert nav.loaded == ['b', 'a']
    assert [s.id for s in nav.visible(sessions)] == ['a1', 'a2']
    assert len(sessions) == 3


def test_remember_active_and_empty_scope():
    nav = WorkspaceNavigation(['a', 'b'], 'a')
    sessions = [S(id='a1', profile_id='a'), S(id='a2', profile_id='a')]
    nav.remember(sessions[1])
    nav.select('b')
    assert nav.active(sessions) is None
    nav.select('a')
    assert nav.active(sessions).id == 'a2'


def test_session_age_uses_monotonic_clock_and_freezes():
    now = [100.0]
    age = SessionAge(lambda: now[0])
    assert age.seconds() is None
    now[0] = 200
    age.start()
    now[0] = 242
    assert age.seconds() == 42
    age.stop()
    now[0] = 600
    assert age.seconds() == 42
    fresh = SessionAge(lambda: now[0]); fresh.start()
    assert fresh.seconds() == 0
    assert [format_duration(n) for n in (None, 42, 720, 7440)] == ['—', '42s', '12m', '2h 04m']
