from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

DEFAULT_SETTINGS = {
    "theme": "Classic Dark",
    "hotkeys": {
        "tool_brush": "1",
        "tool_fill": "2",
        "tool_replace": "3",
        "tool_line": "4",
        "tool_magic": "5",
        "undo": "z",
        "redo": "y",
        "swap_colors": "x",
        "zoom_in": "w",
        "zoom_out": "s",
        "brush_prev": "a",
        "brush_next": "d",
        "crop_selection": "k",
        "toggle_grid": "g",
    },
}


def settings_path(root: Path) -> Path:
    return root / "parapaint_settings.json"


def load_settings(root: Path) -> Dict:
    path = settings_path(root)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_SETTINGS, indent=2), encoding="utf-8")
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged["hotkeys"] = dict(DEFAULT_SETTINGS["hotkeys"])
    merged.update({k: v for k, v in data.items() if k != "hotkeys"})
    if isinstance(data.get("hotkeys"), dict):
        merged["hotkeys"].update(data["hotkeys"])
    return merged
