import json

import pytest

import print3d.cli
import print3d.paths
from print3d.cli import main
from print3d.handoff import machine_line
from print3d.paths import PACKAGE, default_profiles_dir
from print3d.pipeline import PipelineError, _colour_note, run_job
from print3d.printers import BED_TYPES, PrinterError, bed_for, current_printer, machine_facts, save_printer

X2D = PACKAGE / "profiles" / "x2d-0.4"
X1C = PACKAGE / "profiles" / "x1c-0.4"


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
    facts = machine_facts(X1C)
    assert bed_for("PLA", facts=facts) == "Cool Plate"
    assert bed_for("PETG", facts=facts) == "Textured PEI Plate"  # machine.json default_bed_type
    assert bed_for("PLA", "Textured PEI Plate", facts=facts) == "Textured PEI Plate"


def test_bed_must_be_known_and_owned():
    save_printer(owned=["Textured PEI Plate", "Cool Plate"])
    with pytest.raises(PrinterError, match="Cool Plate") as error:  # lists the owned plates
        bed_for("PLA", "Engineering Plate", facts=machine_facts(X2D))
    assert "--bed" in str(error.value) and "print3d printer set --plate PLA=" in str(error.value)
    with pytest.raises(PrinterError, match="Supertack Plate"):  # lists all BED_TYPES
        save_printer(owned=["Glass Plate"])


def test_material_plate_must_be_owned():
    with pytest.raises(PrinterError, match="Textured PEI Plate"):
        save_printer(owned=["Textured PEI Plate"], by_material={"PLA": "Cool Plate"})


def test_dropping_an_owned_plate_names_the_stale_material(tmp_path):
    save_printer(owned=["Textured PEI Plate", "Cool Plate"], by_material={"PLA": "Cool Plate"})
    before = (tmp_path / "printer.json").read_text()
    with pytest.raises(PrinterError, match=r"PLA.*Cool Plate.*--plate PLA="):
        save_printer(owned=["Textured PEI Plate"])
    assert (tmp_path / "printer.json").read_text() == before


def test_save_refuses_to_write_back_an_unknown_printer(tmp_path):
    (tmp_path / "printer.json").write_text('{"printer": "p1s-0.4"}')
    with pytest.raises(PrinterError, match="x1c-0.4"):
        save_printer(owned=["Textured PEI Plate"])
    assert json.loads((tmp_path / "printer.json").read_text()) == {"printer": "p1s-0.4"}
    assert save_printer(key="x1c-0.4")["printer"] == "x1c-0.4"  # the repair still works


@pytest.mark.parametrize(
    "saved",
    ['{"owned": null}', '{"owned": "Cool Plate"}', '{"owned": [1]}', '{"by_material": ["PLA"]}',
     '{"by_material": null}', '{"by_material": {"PLA": 1}}', '{"printer": null}'],
)
def test_wrong_types_in_printer_json_name_the_file(tmp_path, capsys, saved):
    (tmp_path / "printer.json").write_text(saved)
    with pytest.raises(PrinterError, match=r"printer\.json.*Fix it, or delete it"):
        current_printer()
    assert main(["printer", "show"]) == 1
    assert "printer.json" in capsys.readouterr().err


def test_machine_facts_of_pinned_x2d():
    facts = machine_facts(X2D)
    assert facts.model == "Bambu Lab X2D"
    assert facts.nozzles == 2
    assert facts.bed_mm == (256.0, 256.0, 261.0)
    assert facts.default_bed == "Textured PEI Plate"
    # machine.json: not_support_bed_type = "Cool Plate"
    assert facts.beds == ("Engineering Plate", "High Temp Plate", "Textured PEI Plate", "Supertack Plate")


def test_x1c_pla_cannot_use_the_engineering_plate():
    # filament.json: eng_plate_temp = ["0"], Studio's "does not support this plate".
    assert machine_facts(X1C).beds == ("Cool Plate", "High Temp Plate", "Textured PEI Plate", "Supertack Plate")


def test_beds_from_machine_and_filament(tmp_path):
    machine = json.loads((X1C / "machine.json").read_text())
    machine["not_support_bed_type"] = " Cool Plate ;High Temp Plate;"
    (tmp_path / "machine.json").write_text(json.dumps(machine))
    (tmp_path / "filament.json").write_text(json.dumps({"eng_plate_temp": "0", "supertack_plate_temp": ["0"]}))
    assert machine_facts(tmp_path).beds == ("Textured PEI Plate",)
    del machine["not_support_bed_type"]
    (tmp_path / "machine.json").write_text(json.dumps(machine))
    (tmp_path / "filament.json").write_text("{}")
    assert machine_facts(tmp_path).beds == BED_TYPES


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
    save_printer(owned=["Textured PEI Plate", "Supertack Plate"], by_material={"PLA": "Supertack Plate"})
    report = run_job("cube", mesh=cube_stl, jobs_dir=tmp_path / "jobs", execute=False)
    command = report["slice_plan"]["command"]
    assert command[command.index("--curr-bed-type") + 1] == "Supertack Plate"
    assert (report["printer"], report["bed_type"]) == ("x2d-0.4", "Supertack Plate")
    report = run_job("cube", mesh=cube_stl, bed="Textured PEI Plate", jobs_dir=tmp_path / "jobs", execute=False)
    assert report["bed_type"] == "Textured PEI Plate"


def test_x2d_refuses_the_cool_plate(tmp_path, cube_stl):
    supported = "Engineering Plate, High Temp Plate, Textured PEI Plate, Supertack Plate"
    with pytest.raises(PrinterError, match=supported) as error:
        run_job("cube", mesh=cube_stl, bed="Cool Plate", jobs_dir=tmp_path / "jobs", execute=False)
    assert "Bambu Lab X2D" in str(error.value) and "print3d printer set --plate PLA=" in str(error.value)
    assert not (tmp_path / "jobs").exists()  # refused before any job file is touched


def test_x1c_refuses_the_engineering_plate_for_pla(tmp_path, cube_stl):
    save_printer(key="x1c-0.4", by_material={"PLA": "Engineering Plate"})
    with pytest.raises(PrinterError, match="Cool Plate, High Temp Plate, Textured PEI Plate, Supertack Plate"):
        run_job("cube", mesh=cube_stl, jobs_dir=tmp_path / "jobs", execute=False)
    with pytest.raises(PrinterError, match="Engineering Plate"):
        run_job("cube", mesh=cube_stl, bed="Engineering Plate", jobs_dir=tmp_path / "jobs", execute=False)


def test_x1c_takes_the_cool_plate(tmp_path, cube_stl):
    save_printer(key="x1c-0.4")
    report = run_job("cube", mesh=cube_stl, bed="Cool Plate", jobs_dir=tmp_path / "jobs", execute=False)
    assert (report["printer"], report["bed_type"]) == ("x1c-0.4", "Cool Plate")


@pytest.fixture
def no_tools(monkeypatch):
    monkeypatch.setattr(print3d.cli, "find_blender", lambda: "/blender")
    monkeypatch.setattr(print3d.cli, "find_studio", lambda: "/studio")


def test_status_shows_the_printer_and_its_plates(capsys, no_tools):
    save_printer(key="x1c-0.4", owned=["Textured PEI Plate", "Cool Plate"])
    assert main(["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert (status["printer"], status["printer_name"]) == ("x1c-0.4", "Bambu Lab X1 Carbon")
    assert status["beds_owned"] == ["Textured PEI Plate", "Cool Plate"]
    assert status["bed_mm"] == [256.0, 256.0, 250.0]
    assert status["beds_supported"] == ["Cool Plate", "High Temp Plate", "Textured PEI Plate", "Supertack Plate"]
    assert status["profiles_present"] is True


def test_status_without_profiles_names_the_flatten_command(tmp_path, monkeypatch, capsys, no_tools):
    monkeypatch.setattr(print3d.paths, "PACKAGE", tmp_path)  # no profiles/ under it
    save_printer(key="x1c-0.4")
    assert main(["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["profiles_present"] is False
    assert "bed_mm" not in status and "beds_supported" not in status
    assert "print3d flatten --printer x1c-0.4" in status["hint"]


def test_plan_uses_the_configured_plate(tmp_path, capsys, cube_stl):
    save_printer(by_material={"PLA": "Supertack Plate"})
    assert main(["plan", str(cube_stl), str(tmp_path / "out.gcode.3mf")]) == 0
    command = json.loads(capsys.readouterr().out)["command"]
    assert command[command.index("--curr-bed-type") + 1] == "Supertack Plate"


def test_flatten_for_a_named_printer_ignores_a_broken_printer_json(tmp_path, monkeypatch):
    (tmp_path / "printer.json").write_text("{not json")
    seen = {}
    monkeypatch.setattr(print3d.cli, "flatten_printer",
                        lambda printer, output_dir: seen.update(key=printer.key, out=output_dir) or {})
    assert main(["flatten", "--printer", "x1c-0.4"]) == 0
    assert seen == {"key": "x1c-0.4", "out": PACKAGE / "profiles" / "x1c-0.4"}
