import json

import pytest

import print3d.paths
from print3d.cli import main
from print3d.handoff import machine_line
from print3d.paths import PACKAGE, default_profiles_dir
from print3d.pipeline import PipelineError, _colour_note, run_job
from print3d.printers import PrinterError, bed_for, current_printer, machine_facts, save_printer


def test_default_is_x2d_without_config():
    assert current_printer().key == "x2d-0.4"
    assert default_profiles_dir().name == "x2d-0.4"


def test_set_x1c_switches_profiles_dir():
    save_printer(key="x1c-0.4")
    assert current_printer().machine == "Bambu Lab X1 Carbon 0.4 nozzle"
    assert default_profiles_dir().name == "x1c-0.4"


def test_unknown_printer_lists_known():
    with pytest.raises(PrinterError, match="x1c-0.4"):
        save_printer(key="p1s-0.4")


def test_corrupt_config_names_its_path(tmp_path):
    (tmp_path / "printer.json").write_text("{not json")
    with pytest.raises(PrinterError, match="printer.json"):
        current_printer()


def test_unknown_printer_in_file_lists_known(tmp_path):
    (tmp_path / "printer.json").write_text('{"printer": "p1s-0.4"}')
    with pytest.raises(PrinterError, match="x2d-0.4"):
        current_printer()


def test_save_merges_with_existing_file():
    save_printer(key="x1c-0.4", owned=["Cool Plate"])
    shown = save_printer(by_material={"PLA": "Cool Plate"})
    assert shown["printer"] == "x1c-0.4"
    assert shown["owned"] == ["Cool Plate"]
    assert shown["by_material"] == {"PLA": "Cool Plate"}


def test_bed_for_explicit_then_material_then_default():
    save_printer(key="x1c-0.4", owned=["Textured PEI Plate", "Cool Plate"], by_material={"PLA": "Cool Plate"})
    assert bed_for("PLA") == "Cool Plate"
    assert bed_for("PETG") == "Textured PEI Plate"
    assert bed_for("PLA", "Textured PEI Plate") == "Textured PEI Plate"


def test_bed_must_be_known_and_owned():
    save_printer(owned=["Textured PEI Plate", "Cool Plate"])
    with pytest.raises(PrinterError, match="Cool Plate"):  # lists the owned plates
        bed_for("PLA", "Engineering Plate")
    with pytest.raises(PrinterError, match="Supertack Plate"):  # lists all BED_TYPES
        save_printer(owned=["Glass Plate"])


def test_material_plate_must_be_owned():
    with pytest.raises(PrinterError, match="Textured PEI Plate"):
        save_printer(owned=["Textured PEI Plate"], by_material={"PLA": "Cool Plate"})


def test_machine_facts_of_pinned_x2d():
    facts = machine_facts(PACKAGE / "profiles" / "x2d-0.4")
    assert facts.model == "Bambu Lab X2D"
    assert facts.nozzles == 2
    assert facts.bed_mm == (256.0, 256.0, 261.0)
    assert facts.default_bed == "Textured PEI Plate"


def test_cli_printer_set_and_show(capsys):
    assert main(["printer", "set", "--printer", "x1c-0.4", "--owned", "Textured PEI Plate,Cool Plate",
                 "--plate", "PLA=Cool Plate"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["printer"] == "x1c-0.4"
    assert shown["by_material"] == {"PLA": "Cool Plate"}
    assert main(["printer", "show"]) == 0
    assert json.loads(capsys.readouterr().out)["owned"] == ["Textured PEI Plate", "Cool Plate"]


def test_cli_printer_error_is_a_message(capsys):
    assert main(["printer", "set", "--printer", "p1s-0.4"]) == 1
    assert "x1c-0.4" in capsys.readouterr().err


def test_missing_profiles_name_the_flatten_command(tmp_path, monkeypatch, cube_stl):
    monkeypatch.setattr(print3d.paths, "PACKAGE", tmp_path)  # no profiles/ under it
    save_printer(key="x1c-0.4")
    with pytest.raises(PipelineError, match=r"print3d flatten --printer x1c-0.4"):
        run_job("cube", mesh=cube_stl, jobs_dir=tmp_path / "jobs", execute=False)


def test_machine_facts_of_pinned_x1c():
    profiles = PACKAGE / "profiles" / "x1c-0.4"
    facts = machine_facts(profiles)
    assert facts.model == "Bambu Lab X1 Carbon"
    assert facts.nozzles == 1
    assert facts.bed_mm[:2] == (256.0, 256.0)
    assert json.loads((profiles / "process.json").read_text())["enable_support"] == "0"


def test_colour_note_one_nozzle_mentions_ams():
    note = _colour_note(2, 1)
    assert note.code == "colours" and note.severity == "note" and "AMS" in note.message
    assert _colour_note(2, 2) is None
    assert _colour_note(3, 2).message.startswith("3 colours on 2 nozzles")


def test_machine_line_from_report_and_fallback():
    assert machine_line({"printer_name": "Bambu Lab X1 Carbon", "bed_type": "Cool Plate"}) == (
        "Bambu Lab X1 Carbon, 0.4 mm nozzle, 0.20 mm layers, Bambu PLA Basic, Cool Plate, supports off"
    )
    assert machine_line({}).startswith("Bambu Lab X2D, ")


def test_bed_reaches_the_slice_command(tmp_path, cube_stl):
    save_printer(owned=["Textured PEI Plate", "Cool Plate"], by_material={"PLA": "Cool Plate"})
    report = run_job("cube", mesh=cube_stl, jobs_dir=tmp_path / "jobs", execute=False)
    command = report["slice_plan"]["command"]
    assert command[command.index("--curr-bed-type") + 1] == "Cool Plate"
    assert (report["printer"], report["bed_type"]) == ("x2d-0.4", "Cool Plate")
    report = run_job("cube", mesh=cube_stl, bed="Textured PEI Plate", jobs_dir=tmp_path / "jobs", execute=False)
    assert report["bed_type"] == "Textured PEI Plate"
