"""Non-overlapping background snapshots; all Qt delivery queued to GUI."""
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QObject, pyqtSignal

from .port_monitor import Listener, OwnerIdentity, collect_windows_listeners, is_localhost, map_ports


class BackgroundWork(QObject):
    completed = pyqtSignal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ports-work")
        self.closed = False

    def submit(self, work, success, failure=None):
        if self.closed:
            return
        future = self.pool.submit(work)
        def done(result):
            try:
                value = result.result()
                error = None
            except Exception as exc:
                value, error = None, str(exc)
            if not self.closed:
                self.completed.emit(success if error is None else failure, value, error)
        future.add_done_callback(done)

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)


def collect_snapshot(sessions):
    windows = collect_windows_listeners()
    members, roots, children = {}, {}, {}
    wsl_owned, wsl_external = {}, {}
    errors = []
    for session in sessions:
        if session._closed.is_set() or not session.pty:
            continue
        if session.shell == "wsl":
            if not session.wsl:
                continue
            owned = []
            for item in session.wsl.listeners():
                if not is_localhost(item.address):
                    continue
                owner = OwnerIdentity("wsl", item.pid, item.start, item.name, session.distro) if item.pid else None
                listener = Listener(item.address, item.port, owner, "wsl", session.distro)
                if item.session_owned:
                    owned.append(listener)
                else:
                    key = (session.distro, item.address, item.port, item.pid)
                    wsl_external[key] = listener
            wsl_owned[session.id] = owned
            children[session.id] = []
        else:
            infos = session.pty.descendant_infos()
            children[session.id] = infos
            members[session.id] = {item["pid"] for item in infos}
            roots[session.id] = session.pty.pid
            error = getattr(session.pty, "attribution_error", "")
            if error:
                errors.append(error)
    attributed, external = map_ports(members, windows, roots)
    attributed.update(wsl_owned)
    owned_keys = {(l.distro, l.address, l.port, l.owner.pid if l.owner else None)
                  for group in wsl_owned.values() for l in group}
    external.extend(l for key, l in wsl_external.items() if key not in owned_keys)
    # Keep Windows forwarders as separate environment entries until an actual
    # mapping is known; matching port numbers alone do not establish identity.
    return attributed, external, children, errors
