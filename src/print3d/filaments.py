"""Coloured copies of the pinned filament, one per colour a job asks for.

Colour is the only thing that changes: the material stays the pinned Bambu PLA
Basic, so every check and the slice keep meaning the same thing. Studio puts
the first filaments on the printer's nozzles (two on an X2D, one on an X1 Carbon);
any beyond that are swapped in on one of them, with a purge per change.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Bambu PLA Basic, as the colours are named on the spool.
COLOURS = {
    "white": "#FFFFFF",
    "black": "#000000",
    "grey": "#8E9089",
    "gray": "#8E9089",
    "silver": "#A6A9AA",
    "red": "#C12E1F",
    "orange": "#FF6A13",
    "yellow": "#F4EE2A",
    "green": "#00AE42",
    "blue": "#0A2989",
    "cyan": "#0086D6",
    "purple": "#5E43B7",
    "pink": "#F55A74",
    "magenta": "#EC008C",
    "brown": "#9D432C",
    "beige": "#F7E6DE",
    "gold": "#E4BD68",
}
DEFAULT_COLOUR = "green"
HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
NOZZLES = 2


class FilamentError(ValueError):
    """Raised for a colour that is neither a known name nor #RRGGBB."""


def colour_hex(colour: str | None) -> str:
    name = (colour or DEFAULT_COLOUR).strip().lower()
    if name in COLOURS:
        return COLOURS[name]
    if HEX_RE.match(name):
        return "#" + name.lstrip("#").upper()
    raise FilamentError(
        f"Unknown colour {colour!r}. Use #RRGGBB or one of: {', '.join(sorted(COLOURS))}."
    )


def colour_filament(base: Path, colour: str, out_dir: Path) -> Path:
    """The pinned filament with only its colour and name changed."""
    hex_ = colour_hex(colour)
    profile = json.loads(base.read_text(encoding="utf-8"))
    label = f"print3d {colour.strip().lower()} {profile['filament_type'][0]}"
    profile["name"] = label
    profile["filament_settings_id"] = [label]
    profile["filament_colour"] = [hex_]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{hex_.lstrip('#').lower()}.json"
    path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return path


def job_filaments(base: Path, colours: list[str], out_dir: Path) -> list[Path]:
    """One filament per colour, in order. The colour list is already de-duplicated."""
    return [colour_filament(base, colour, out_dir) for colour in colours]
