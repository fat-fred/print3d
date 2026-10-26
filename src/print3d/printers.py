"""Which printer to slice for, and which build plates you own.

The pinned profiles under profiles/<key> belong to one printer each. The choice
and the plates live in ~/print3d/printer.json, so a printer is picked once and
the same file answers for the CLI, the MCP server and the agent. Without the
file print3d targets the Bambu Lab X2D, as it always has.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from print3d.flatten import DEFAULT_BED_TYPE, DEFAULT_FILAMENT, DEFAULT_MACHINE, DEFAULT_PROCESS

PRINTER_ENV = "PRINT3D_PRINTER"
# Bambu Studio's names for the plates, as --curr-bed-type and the profiles spell them.
BED_TYPES = ("Cool Plate", "Engineering Plate", "High Temp Plate", "Textured PEI Plate", "Supertack Plate")
DEFAULT_PRINTER = "x2d-0.4"


class PrinterError(ValueError):
    pass


@dataclass(frozen=True)
class Printer:
    key: str
    name: str
    machine: str
    process: str
    filament: str
    bed_type: str


PRINTERS = {
    "x2d-0.4": Printer(
        "x2d-0.4", "Bambu Lab X2D", DEFAULT_MACHINE, DEFAULT_PROCESS, DEFAULT_FILAMENT, DEFAULT_BED_TYPE
    ),
    "x1c-0.4": Printer(
        "x1c-0.4",
        "Bambu Lab X1 Carbon",
        "Bambu Lab X1 Carbon 0.4 nozzle",
        "0.20mm Standard @BBL X1C",
        "Bambu PLA Basic @BBL X1C",
        "Textured PEI Plate",
    ),
}


@dataclass(frozen=True)
class MachineFacts:
    model: str
    bed_mm: tuple[float, float, float]
    nozzles: int
    default_bed: str


def printer_path() -> Path:
    if env := os.environ.get(PRINTER_ENV, "").strip():
        return Path(env).expanduser()
    return Path.home() / "print3d" / "printer.json"


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrinterError(f"Cannot read {path}: {exc}. Fix it, or delete it for the {DEFAULT_PRINTER} default.") from exc
    if not isinstance(saved, dict):
        raise PrinterError(f"{path} must hold a JSON object. Fix it, or delete it for the {DEFAULT_PRINTER} default.")
    return saved


def load_printer() -> dict[str, Any]:
    path = printer_path()
    saved = _read(path)
    return {
        "printer": saved.get("printer", DEFAULT_PRINTER),
        "owned": list(saved.get("owned", [])),
        "by_material": dict(saved.get("by_material", {})),
        "path": str(path),
    }


def _check_printer(key: str) -> Printer:
    if key not in PRINTERS:
        raise PrinterError(f"Unknown printer {key!r}. Printers are: {', '.join(PRINTERS)}.")
    return PRINTERS[key]


def _check_bed(bed: str) -> str:
    if bed not in BED_TYPES:
        raise PrinterError(f"Unknown plate {bed!r}. Plates are: {', '.join(BED_TYPES)}.")
    return bed


def _check_owned(bed: str, owned: list[str]) -> str:
    if owned and bed not in owned:
        raise PrinterError(f"You do not own the {bed}. Your plates are: {', '.join(owned)}.")
    return bed


def current_printer() -> Printer:
    return _check_printer(load_printer()["printer"])


def save_printer(
    key: str | None = None,
    owned: list[str] | None = None,
    by_material: dict[str, str] | None = None,
) -> dict[str, Any]:
    saved = load_printer()
    if key is not None:
        saved["printer"] = _check_printer(key).key
    if owned is not None:
        saved["owned"] = [_check_bed(bed) for bed in dict.fromkeys(owned)]
    if by_material is not None:
        saved["by_material"] = {**saved["by_material"], **{m: _check_bed(b) for m, b in by_material.items()}}
    for bed in saved["by_material"].values():
        _check_owned(_check_bed(bed), saved["owned"])
    path = printer_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {k: saved[k] for k in ("printer", "owned", "by_material")}
    path.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    return load_printer()


def bed_for(material: str, bed: str | None = None) -> str:
    """The plate to print on: the one asked for, else the one set for the material, else the printer's own."""
    saved = load_printer()
    chosen = bed or saved["by_material"].get(material) or current_printer().bed_type
    return _check_owned(_check_bed(chosen), saved["owned"])


def machine_facts(profiles_dir: Path) -> MachineFacts:
    """What the pinned machine.json says about the printer: bed size, nozzles, default plate."""
    machine = json.loads((profiles_dir / "machine.json").read_text(encoding="utf-8"))
    corners = [tuple(float(v) for v in point.strip().split("x")) for point in machine["printable_area"]]
    return MachineFacts(
        model=machine["printer_model"],
        bed_mm=(
            max(x for x, _ in corners) - min(x for x, _ in corners),
            max(y for _, y in corners) - min(y for _, y in corners),
            float(machine["printable_height"]),
        ),
        nozzles=len(machine["nozzle_diameter"]),
        default_bed=machine["default_bed_type"],
    )
