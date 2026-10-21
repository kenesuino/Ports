from ports.session_manager import TerminalSession, SessionManager


class FakePty:
    def __init__(self): self.writes = []; self.interrupts = 0
    def write(self, value): self.writes.append(value)
    def isalive(self): return True
    def send_ctrl_c(self): self.interrupts += 1


def test_startup_waits_for_prompt_and_runs_once():
    session = TerminalSession("API", "pwsh", "", "python api.py")
    session.pty = FakePty()
    session.state = "starting"
    session._on_prompt("C:/work")
    session._on_prompt("C:/work")
    assert session.pty.writes == ["python api.py\r"]
    assert session.current_cwd == "C:/work"


def test_user_input_cancels_restart_replay():
    session = TerminalSession("API", "pwsh", "", "python api.py")
    session.pty = FakePty()
    session._startup_pending = False
    session.state = "running"
    session.restart()
    session._on_input("x")
    session._on_prompt("C:/work")
    assert session.pty.writes == ["x"]


def test_profile_run_focuses_existing_instance_without_duplicates():
    from ports.profiles import WorkspaceProfile, TerminalProfile
    manager = SessionManager()
    profile = WorkspaceProfile(name="dev", terminals=[TerminalProfile(name="api")])
    first = manager.launch_profile(profile)
    again = manager.launch_profile(profile)
    assert first == again
    assert len(manager.sessions) == 1
    assert len(manager.launch_profile(profile, duplicate=True)) == 1
    assert len(manager.sessions) == 2
