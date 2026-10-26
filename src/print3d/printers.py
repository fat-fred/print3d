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
from typing import Any, Literal, get_args

from print3d.flatten import DEFAULT_BED_TYPE, DEFAULT_FILAMENT, DEFAULT_MACHINE, DEFAULT_PROCESS

PRINTER_ENV = "PRINT3D_PRINTER"
# Bambu Studio's names for the plates, as --curr-bed-type and the profiles spell them.
BedType = Literal["Cool Plate", "Engineering Plate", "High Temp Plate", "Textured PEI Plate", "Supertack Plate"]
BED_TYPES: tuple[str, ...] = get_args(BedType)
# The filament.json bed temperature per plate; "0" means the filament cannot print on it.
BED_TEMPS = {
    "Cool Plate": "cool_plate_temp",
    "Engineering Plate": "eng_plate_temp",
    "High Temp Plate": "hot_plate_temp",
    "Textured PEI Plate": "textured_plate_temp",
    "Supertack Plate": "supertack_plate_temp",
}
DEFAULT_PRINTER = "x2d-0.4"


class PrinterError(ValueError):
    """Raised when printer.json, or the plate asked for, does not fit the printer."""


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
    beds: tuple[str, ...]


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


def _malformed(path: Path, key: str, want: str) -> PrinterError:
    return PrinterError(f'{path}: "{key}" must be {want}. Fix it, or delete it for the {DEFAULT_PRINTER} default.')


def _texts(values: Any) -> bool:
    return isinstance(values, list) and all(isinstance(value, str) for value in values)


def load_printer() -> dict[str, Any]:
    path = printer_path()
    saved = _read(path)
    printer = saved.get("printer", DEFAULT_PRINTER)
    owned = saved.get("owned", [])
    by_material = saved.get("by_material", {})
    if not isinstance(printer, str):
        raise _malformed(path, "printer", 'a printer key, e.g. "x1c-0.4"')
    if not _texts(owned):
        raise _malformed(path, "owned", 'a list of plates, e.g. ["Textured PEI Plate"]')
    if not (isinstance(by_material, dict) and _texts(list(by_material.values()))):
        raise _malformed(path, "by_material", 'an object of material to plate, e.g. {"PLA": "Cool Plate"}')
    return {"printer": printer, "owned": list(owned), "by_material": dict(by_material), "path": str(path)}


def _check_printer(key: str) -> Printer:
    if key not in PRINTERS:
        raise PrinterError(f"Unknown printer {key!r}. Printers are: {', '.join(PRINTERS)}.")
    return PRINTERS[key]


def _check_bed(bed: str) -> str:
    if bed not in BED_TYPES:
        raise PrinterError(f"Unknown plate {bed!r}. Plates are: {', '.join(BED_TYPES)}.")
    return bed


def _remedy(material: str) -> str:
    return f'Pass --bed (bed= in make) with one of them, or set one: print3d printer set --plate {material}="<plate>".'


def current_printer() -> Printer:
    return _check_printer(load_printer()["printer"])


def save_printer(
    key: str | None = None,
    owned: list[str] | None = None,
    by_material: dict[str, str] | None = None,
) -> dict[str, Any]:
    saved = load_printer()
    if key is not None:
        saved["printer"] = key
    _check_printer(saved["printer"])  # a stored unknown key is not written back
    if owned is not None:
        saved["owned"] = list(dict.fromkeys(owned))
    saved["owned"] = [_check_bed(bed) for bed in saved["owned"]]
    if by_material is not None:
        saved["by_material"] = {**saved["by_material"], **{m: _check_bed(b) for m, b in by_material.items()}}
    for material, bed in saved["by_material"].items():
        if saved["owned"] and _check_bed(bed) not in saved["owned"]:
            raise PrinterError(
                f"{material} is set to the {bed}, which is not among your plates ({', '.join(saved['owned'])}). "
                f"Change it with --plate {material}=\"<plate>\", or add the {bed} to --owned."
            )
    path = printer_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {k: saved[k] for k in ("printer", "owned", "by_material")}
    path.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    return load_printer()


def bed_for(material: str, bed: str | None = None, *, facts: MachineFacts) -> str:
    """The plate to print on: the one asked for, else the one set for the material, else the printer's default.

    Refused unless you own it and the printer and its pinned filament can print on it.
    """
    saved = load_printer()
    chosen = _check_bed(bed or saved["by_material"].get(material) or facts.default_bed)
    if saved["owned"] and chosen not in saved["owned"]:
        raise PrinterError(
            f"You do not own the {chosen}. Your plates are: {', '.join(saved['owned'])}. {_remedy(material)}"
        )
    if chosen not in facts.beds:
        raise PrinterError(
            f"The {facts.model} with its pinned filament cannot print on the {chosen}. "
            f"Plates it can print on: {', '.join(facts.beds)}. {_remedy(material)}"
        )
    return chosen


def _zero(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return bool(values) and all(str(v).strip() == "0" for v in values)


def machine_facts(profiles_dir: Path) -> MachineFacts:
    """What the pinned profiles say about the printer: bed size, nozzles, default plate, usable plates."""
    machine = json.loads((profiles_dir / "machine.json").read_text(encoding="utf-8"))
    filament = json.loads((profiles_dir / "filament.json").read_text(encoding="utf-8"))
    corners = [tuple(float(v) for v in point.strip().split("x")) for point in machine["printable_area"]]
    unsupported = {bed.strip() for bed in (machine.get("not_support_bed_type") or "").split(";")}
    return MachineFacts(
        model=machine["printer_model"],
        bed_mm=(
            max(x for x, _ in corners) - min(x for x, _ in corners),
            max(y for _, y in corners) - min(y for _, y in corners),
            float(machine["printable_height"]),
        ),
        nozzles=len(machine["nozzle_diameter"]),
        default_bed=machine["default_bed_type"],
        beds=tuple(bed for bed in BED_TYPES if bed not in unsupported and not _zero(filament.get(BED_TEMPS[bed]))),
    )
