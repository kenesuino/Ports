"""Workspace navigation coordination, shared by the desktop and its controls."""
import uuid
from .workspace_navigation import OTHER


class NavigationActions:
    def _save_navigation(self):
        self.config.loaded_workspace_ids = list(self.navigation.loaded)
        self.config.selected_workspace_id = self.navigation.selected
        self.save_config()

    def load_workspace(self, identifier):
        if not any(p.id == identifier for p in self.config.profiles): return
        self.navigation.remember(self.manager.active)
        self.navigation.load(identifier)
        if identifier not in self.config.expanded_workspace_ids:
            self.config.expanded_workspace_ids.append(identifier)
        self._select_current_scope()
        self._save_navigation()

    def select_scope(self, identifier):
        self.navigation.remember(self.manager.active)
        self.navigation.select(identifier)
        self._select_current_scope()
        self._save_navigation()

    def _select_current_scope(self):
        self.manager.set_active(self.navigation.active(self.manager.sessions))
        self.refresh_navigation()
        self._refresh_merged_ports()

    def unpin_workspace(self, identifier):
        self.navigation.remember(self.manager.active)
        self.navigation.unpin(identifier)
        self._select_current_scope()
        self._save_navigation()

    def visible_sessions(self):
        return self.navigation.visible(self.manager.sessions)

    def focus_session(self, session):
        if session is None: return
        self.navigation.remember(self.manager.active)
        self.navigation.select(self.navigation.scope(session))
        self.manager.set_active(session)
        self.refresh_navigation()
        self._save_navigation()

    def _reorder_visible(self, identifiers):
        self.manager.reorder(self.navigation.reordered(self.manager.sessions, identifiers))

    def _expansion_changed(self, expanded):
        self.config.expanded_workspace_ids = expanded
        self.save_config()

    def _create_ad_hoc(self, values):
        profile = self._selected_profile()
        metadata = {}
        if profile:
            active = self.manager.active
            instance = active.instance_id if active and active.profile_id == profile.id else next((s.instance_id for s in self.visible_sessions()), uuid.uuid4().hex)
            metadata = dict(profile_id=profile.id, instance_id=instance)
        self.manager.create(**values, **metadata)

    def _tree_action(self, action, row):
        handlers = {'start': self._panel_start, 'edit': self._panel_edit,
                    'rename': self._panel_rename, 'close': self._panel_close, 'retry': self._panel_retry}
        if action == 'copy-terminal':
            definition = row.get('definition')
            profile = next((p for p in self.config.profiles if p.id == row.get('scope')), None)
            if profile and definition and (not profile.needs_review() or self._review_profile(profile)):
                self.manager.launch_definition(profile, definition.id, uuid.uuid4().hex)
        elif action in handlers: handlers[action](row)
