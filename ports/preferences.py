"""Sectioned, validated Preferences dialog.

Values are applied to the config object only on Save, so Cancel never mutates
state. Validation is reported inline next to the field that failed.
"""

from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from . import config_store
from .theme import (
    DESTRUCTIVE, LISTENING, SPACE_1, SPACE_2, SPACE_3, TEXT_MUTED,
)

_ENTRY_RE = re.compile(r"^[\w .\-\[\]\(\)@]+$")
SECTIONS = ("General", "Appearance", "Ports", "Recovery", "About")


class PreferencesDialog(QDialog):
    """Left section list, right page, one Save for the whole dialog."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Preferences")
        self.resize(760, 520)
        self.result_config = config

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        root.setSpacing(SPACE_2)

        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter settings…")
        self.filter_box.setAccessibleName("Filter settings")
        self.filter_box.textChanged.connect(self._filter_sections)
        root.addWidget(self.filter_box)

        body = QHBoxLayout()
        body.setSpacing(SPACE_3)
        self.sections = QListWidget()
        self.sections.setFixedWidth(160)
        self.sections.setAccessibleName("Settings sections")
        for name in SECTIONS:
            self.sections.addItem(name)
        self.sections.currentRowChanged.connect(self._show_section)
        body.addWidget(self.sections)

        self.pages = QStackedWidget()
        self._build_pages()
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)

        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Save).setText("Save")
        controls.accepted.connect(self._save)
        controls.rejected.connect(self.reject)
        root.addWidget(controls)

        self.sections.setCurrentRow(0)

    # -- pages -----------------------------------------------------------

    def _page(self) -> tuple[QWidget, QFormLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        host = QWidget()
        form = QFormLayout(host)
        form.setContentsMargins(SPACE_2, SPACE_2, SPACE_2, SPACE_2)
        form.setSpacing(SPACE_2)
        scroll.setWidget(host)
        return scroll, form

    def _build_pages(self) -> None:
        general, form = self._page()
        self.scrollback = QSpinBox()
        self.scrollback.setRange(100, 100000)
        self.scrollback.setSingleStep(500)
        self.scrollback.setValue(int(getattr(self.config, "scrollback_lines", 10000)))
        self.scrollback.setSuffix(" lines")
        form.addRow("Retained scrollback", self.scrollback)

        self.font_size = QSpinBox()
        self.font_size.setRange(9, 20)
        self.font_size.setValue(int(getattr(self.config, "terminal_font_size", 13)))
        self.font_size.setSuffix(" pt")
        form.addRow("Terminal font size", self.font_size)

        self.copy_select = QCheckBox("Copy terminal selection to the clipboard")
        self.copy_select.setChecked(bool(getattr(self.config, "copy_on_select", True)))
        form.addRow(self.copy_select)

        note = QLabel('Loaded workspace names and groups are remembered. Shells and commands never start automatically on launch.')
        note.setWordWrap(True)
        form.addRow(note)
        self.pages.addWidget(general)

        appearance, form = self._page()
        self.motion = QComboBox()
        for text, value in (("Follow Windows", "system"),
                            ("Reduce motion", "on"), ("Enable motion", "off")):
            self.motion.addItem(text, value)
        self.motion.setCurrentIndex(
            max(0, self.motion.findData(getattr(self.config, "reduced_motion",
                                                "system"))))
        form.addRow("Motion", self.motion)

        self.start_panel = QCheckBox("Start with the Ports inspector visible")
        self.start_panel.setChecked(self.config.ports_inspector_visible)
        form.addRow(self.start_panel)
        self.pages.addWidget(appearance)

        ports, form = self._page()
        note = QLabel(
            "Filters affect only the External group. Ports owned by your "
            "sessions are always shown, and exact port search always sees "
            "every listener.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_MUTED};")
        form.addRow(note)

        self.denylist = QPlainTextEdit("\n".join(
            getattr(self.config, "process_denylist", [])))
        self.denylist.setMaximumHeight(110)
        form.addRow("Never list these processes", self.denylist)

        self.allowlist = QPlainTextEdit("\n".join(
            getattr(self.config, "process_allowlist", [])))
        self.allowlist.setMaximumHeight(90)
        form.addRow("Always list these processes", self.allowlist)

        self.probe_interval = QSpinBox()
        self.probe_interval.setRange(2, 60)
        self.probe_interval.setValue(int(getattr(self.config, "probe_interval", 5)))
        self.probe_interval.setSuffix(" s")
        form.addRow("HTTP check interval", self.probe_interval)
        self.pages.addWidget(ports)

        recovery, form = self._page()
        self.recovery_note = QLabel("")
        self.recovery_note.setWordWrap(True)
        form.addRow(self.recovery_note)
        self.recover_box = QCheckBox(
            "Back up the unreadable file and allow saving again")
        self.recover_box.setVisible(bool(getattr(self.config, "read_only", False)))
        form.addRow(self.recover_box)
        self.pages.addWidget(recovery)

        about, form = self._page()
        for label, text in (
            ("Ports", "Interactive terminal manager with port ownership."),
            ("Runtime", "PyQt6 6.11 · Qt 6.11.2 · Python 3.11+"),
            ("Assets", "Application mark derived from the supplied SVG."),
            ("Licence", "PyQt6 is GPL/commercial; review before distributing."),
        ):
            row = QLabel(f"<b>{label}</b><br>{text}")
            row.setWordWrap(True)
            row.setStyleSheet(f"color:{TEXT_MUTED};" if label != "Ports" else "")
            form.addRow(row)
        self.pages.addWidget(about)

        self._refresh_recovery_note()

    def _refresh_recovery_note(self) -> None:
        warning = getattr(self.config, "warning", "")
        if getattr(self.config, "read_only", False):
            self.recovery_note.setText(
                warning or "The configuration file could not be read.")
            self.recovery_note.setStyleSheet(f"color:{DESTRUCTIVE};")
        else:
            self.recovery_note.setText(
                "Configuration is readable and saves normally.")
            self.recovery_note.setStyleSheet(f"color:{LISTENING};")

    # -- behaviour -------------------------------------------------------

    def _filter_sections(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.sections.count()):
            item = self.sections.item(index)
            item.setHidden(bool(needle) and needle not in item.text().lower())
        if needle:
            for index in range(self.sections.count()):
                if not self.sections.item(index).isHidden():
                    self.sections.setCurrentRow(index)
                    break

    def _show_section(self, index: int) -> None:
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)

    def _parse_list(self, widget: QPlainTextEdit, label: str) -> list[str]:
        values = []
        for line in widget.toPlainText().splitlines():
            entry = line.strip().lower()
            if not entry:
                continue
            if not _ENTRY_RE.match(entry):
                raise ValueError(
                    f"{label}: only letters, digits, spaces and . - _ [ ] ( ) @"
                    f" are allowed — got '{entry}'")
            values.append(entry)
        if len(values) > 256:
            raise ValueError(f"{label}: at most 256 entries")
        return values

    def _save(self) -> None:
        try:
            denylist = self._parse_list(self.denylist, "Process denylist")
            allowlist = self._parse_list(self.allowlist, "Process allowlist")
        except ValueError as exc:
            self._show_error(str(exc))
            self.sections.setCurrentRow(2)
            return

        config = self.config
        config.scrollback_lines = int(self.scrollback.value())
        config.terminal_font_size = int(self.font_size.value())
        config.copy_on_select = self.copy_select.isChecked()
        config.restore_layout = False
        config.reduced_motion = self.motion.currentData()
        config.rail_collapsed = False
        config.ports_inspector_visible = self.start_panel.isChecked()
        config.process_denylist = denylist
        config.process_allowlist = allowlist
        config.probe_interval = int(self.probe_interval.value())
        if config.read_only and self.recover_box.isChecked():
            if not config_store.recover(config):
                self._show_error(
                    "Could not back up the config file: "
                    + getattr(config, "last_error", "unknown error"))
                return
        if not config_store.save(config):
            self._show_error(
                "Settings could not be saved: "
                + getattr(config, "last_error", "unknown error"))
            self._refresh_recovery_note()
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setStyleSheet(f"color:{DESTRUCTIVE};")
        self.error_label.setVisible(True)
