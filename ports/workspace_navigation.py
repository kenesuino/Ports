"""Navigation owns scopes, never processes. Session ages use monotonic time."""
import threading
import time

OTHER = '@other'


class WorkspaceNavigation:
    def __init__(self, loaded=(), selected=OTHER):
        self.loaded = list(dict.fromkeys(loaded))
        self.selected = selected if selected in self.loaded else OTHER
        self.last_active = {}

    def load(self, identifier):
        if identifier not in self.loaded:
            self.loaded.append(identifier)
        self.select(identifier)

    def unpin(self, identifier):
        if identifier in self.loaded:
            self.loaded.remove(identifier)
        if self.selected == identifier:
            self.selected = OTHER

    def select(self, identifier):
        self.selected = identifier if identifier in self.loaded else OTHER

    def scope(self, session):
        return session.profile_id if session.profile_id in self.loaded else OTHER

    def visible(self, sessions):
        return [s for s in sessions if self.scope(s) == self.selected]

    def remember(self, session):
        if session is not None:
            self.last_active[self.scope(session)] = session.id

    def active(self, sessions):
        visible = self.visible(sessions)
        return next((s for s in visible if s.id == self.last_active.get(self.selected)), visible[0] if visible else None)

    def reordered(self, sessions, identifiers):
        visible = {s.id for s in self.visible(sessions)}
        if set(identifiers) != visible or len(identifiers) != len(visible):
            raise ValueError('Tab reorder does not match visible sessions')
        replacement = iter(identifiers)
        return [next(replacement) if s.id in visible else s.id for s in sessions]


def derive_rows(profile, sessions):
    """Keep all instance/definition pairs, including missing definitions."""
    if profile is None:
        return [dict(key=("loose", getattr(s, "id", str(i))), definition=None,
                     session=s, state=s.state, instance_id="", group="Open terminals")
                for i, s in enumerate(sessions)]
    matching = [s for s in sessions if s.profile_id == profile.id]
    instances = list(dict.fromkeys(getattr(s, "instance_id", "") for s in matching)) or [""]
    rows = []
    known = {d.id for d in profile.terminals}
    for number, instance in enumerate(instances, 1):
        members = [s for s in matching if getattr(s, "instance_id", "") == instance]
        group = f"Instance {number}" if instance else "Not started"
        for definition in profile.terminals:
            live = [s for s in members if s.definition_id == definition.id]
            for index, session in enumerate(live or [None]):
                key = (instance, definition.id) if index == 0 else (instance, definition.id, session.id)
                rows.append(dict(key=key, definition=definition, session=session,
                                 state=session.state if session else "stopped",
                                 instance_id=instance, group=group))
        for i, session in enumerate(members):
            if session.definition_id not in known:
                rows.append(dict(key=(instance, "orphan", getattr(session, "id", str(i))),
                                 definition=None, session=session, state=session.state,
                                 instance_id=instance, group=group))
    return rows


class SessionAge:
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.started = self.ended = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.started is None and self.ended is None:
                self.started = self.clock()

    def stop(self):
        with self._lock:
            if self.ended is None:
                self.ended = self.clock()

    def seconds(self):
        with self._lock:
            if self.started is None:
                return None
            return max(0, int((self.ended if self.ended is not None else self.clock()) - self.started))


def format_duration(seconds):
    if seconds is None:
        return '—'
    if seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m'
    return f'{seconds // 3600}h {(seconds % 3600) // 60:02d}m'
