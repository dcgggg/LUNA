from __future__ import annotations

from lfp_analysis.colors import (
    DEFAULT_COLOR_TEMPLATE,
    available_color_templates,
    channel_color,
    channel_colors,
    region_color,
)


def test_color_templates_are_extensible_and_stable() -> None:
    assert len(available_color_templates()) >= 6
    assert len({region_color(f"region-{index}") for index in range(64)}) >= 56
    rows = [{"channel_name": f"ch-{index}", "region": f"region-{index % 12}"} for index in range(64)]
    first = channel_colors(rows, DEFAULT_COLOR_TEMPLATE)
    reordered = channel_colors(list(reversed(rows)), DEFAULT_COLOR_TEMPLATE)
    assert first == reordered
    assert region_color("new-region", DEFAULT_COLOR_TEMPLATE) == region_color("new-region", DEFAULT_COLOR_TEMPLATE)
    assert channel_color("ch-1", "region-1", DEFAULT_COLOR_TEMPLATE) != channel_color("ch-2", "region-1", DEFAULT_COLOR_TEMPLATE)
