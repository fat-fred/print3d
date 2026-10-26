import json
from pathlib import Path

from print3d.flatten import build_name_index, flatten_by_name, flatten_printer, normalize_for_cli
from print3d.printers import PRINTERS


def _fake_bbl_tree(tmp_path: Path, *, machine: str, process: str, filament: str) -> Path:
    for kind, name in (("machine", machine), ("process", process), ("filament", filament)):
        folder = tmp_path / "BBL" / kind
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.json").write_text(
            json.dumps({"type": kind, "name": name, "from": "system"}) + "\n", encoding="utf-8"
        )
    return tmp_path


def test_inherits_and_include(tmp_path: Path):
    vendor = tmp_path / "BBL" / "machine"
    vendor.mkdir(parents=True)
    (vendor / "base.json").write_text(
        '{"type":"machine","name":"base","from":"system","a":1,"b":1}\n',
        encoding="utf-8",
    )
    (vendor / "inc.json").write_text(
        '{"name":"inc","machine_start_gcode":"G28"}\n',
        encoding="utf-8",
    )
    (vendor / "leaf.json").write_text(
        '{"type":"machine","name":"leaf","inherits":"base","include":["inc"],"b":2}\n',
        encoding="utf-8",
    )
    index = build_name_index(tmp_path)
    flat = flatten_by_name("leaf", index)
    assert flat["a"] == 1
    assert flat["b"] == 2
    assert flat["machine_start_gcode"] == "G28"
    normalize_for_cli(flat, "machine", "leaf")
    assert flat["from"] == "User"
    assert flat["inherits"] == "leaf"
    assert flat["printer_settings_id"] == "leaf"
    assert "include" not in flat


def test_flatten_printer_uses_the_printers_leaves(tmp_path):
    root = _fake_bbl_tree(
        tmp_path,
        machine="Bambu Lab X1 Carbon 0.4 nozzle",
        process="0.20mm Standard @BBL X1C",
        filament="Bambu PLA Basic @BBL X1C",
    )
    out = flatten_printer(PRINTERS["x1c-0.4"], output_dir=tmp_path / "out", profiles_root=root)
    assert out["provenance"]["machine"] == "Bambu Lab X1 Carbon 0.4 nozzle"
    process = json.loads((tmp_path / "out" / "process.json").read_text())
    assert process["curr_bed_type"] == "Textured PEI Plate"
    # The fake process does not turn supports off, so flatten does and records it.
    assert process["enable_support"] == "0"
    assert out["provenance"]["overrides"] == {"enable_support": "0"}
    assert json.loads((tmp_path / "out" / "provenance.json").read_text())["overrides"] == {"enable_support": "0"}
