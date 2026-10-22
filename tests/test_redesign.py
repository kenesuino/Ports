"""Regression tests for the tabs-only gray redesign's pure logic."""

from __future__ import annotations

import pytest

from ports import theme
from ports.header_bar import elide_middle
from ports.motion import reduced_motion
from ports.profiles import TerminalProfile, WorkspaceProfile, valid_accent


def test_elide_middle_keeps_last_two_segments():
    assert elide_middle(r"F:\Github\Ports\ports\web\terminal.js") == "…/web/terminal.js"
    assert elide_middle("/home/dev/api") == "…/dev/api"
    assert elide_middle("/srv") == "srv"
    assert elide_middle("") == ""


def test_palette_is_neutral_gray_not_blue():
    """Every surface and text token must be near-equal in RGB channels."""
    tokens = [
        theme.CANVAS, theme.PANEL, theme.RAISED, theme.HOVER, theme.PRESSED,
        theme.BORDER, theme.DIVIDER, theme.TEXT, theme.TEXT_SECONDARY,
        theme.TEXT_MUTED, theme.TEXT_DISABLED, theme.FOCUS,
    ]
    for value in tokens:
        channels = [int(value[i:i + 2], 16) for i in (1, 3, 5)]
        assert max(channels) - min(channels) <= 4, (
            f"{value} is not neutral: {channels}")


def test_semantic_colors_are_distinct_and_not_reused_for_surfaces():
    surfaces = {theme.CANVAS, theme.PANEL, theme.RAISED, theme.BORDER}
    for semantic in (theme.LISTENING, theme.DESTRUCTIVE, theme.WAITING):
        assert semantic not in surfaces


def test_motion_tokens_are_sub_300ms_and_ordered():
    assert 0 < theme.MOTION_FAST < theme.MOTION_PANEL < theme.MOTION_TOAST
    assert theme.MOTION_PANEL <= 300


def test_spacing_scale_is_consistent():
    assert (theme.SPACE_1, theme.SPACE_2, theme.SPACE_3,
            theme.SPACE_4, theme.SPACE_5, theme.SPACE_6) == (4, 8, 12, 16, 20, 24)


def test_reduced_motion_override_wins():
    assert reduced_motion("on")
    assert not reduced_motion("off")


def test_legacy_accents_still_load():
    """Profiles saved before the gray palette must keep opening."""
    assert valid_accent("#7aa2f7")
    assert valid_accent("#e7e7e7")
    assert not valid_accent("blue")
    data = TerminalProfile(name="old").to_dict()
    data["accent"] = "#7dcfff"
    assert TerminalProfile.from_dict(data).accent == "#7dcfff"


def test_workspace_approval_ignores_cosmetic_changes():
    terminal = TerminalProfile(name="api", accent="#e7e7e7")
    profile = WorkspaceProfile(terminals=[terminal])
    profile.approve()
    terminal.accent = "#4fd18b"
    terminal.name = "renamed"
    assert not profile.needs_review()
    terminal.cwd = "/changed"
    assert profile.needs_review()


def test_invalid_accent_rejected():
    data = TerminalProfile().to_dict()
    data["accent"] = "nonsense"
    with pytest.raises(ValueError):
        TerminalProfile.from_dict(data)
