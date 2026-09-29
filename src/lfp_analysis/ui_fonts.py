"""Select an installed UI font without platform-specific absolute font paths."""

FONT_PREFERENCES = {
    "Darwin": ("PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Arial Unicode MS", "Helvetica Neue", "Arial"),
    "Windows": ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI", "Arial"),
    "default": ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei", "DejaVu Sans", "Arial"),
}


def choose_ui_font_family(installed_families: set[str] | list[str] | tuple[str, ...], system: str) -> str:
    available = set(installed_families)
    preferences = FONT_PREFERENCES.get(system, FONT_PREFERENCES["default"])
    return next((family for family in preferences if family in available), "Arial")
