from pathlib import Path

import pytest

from conftest import ascii_stl_box, ascii_stl_cube, write_cube_stl
from print3d.dfm import DfmError, check_mesh, require_printable
from print3d.paths import PACKAGE, default_profiles_dir
from print3d.printers import machine_facts, save_printer


def test_cube_is_printable(tmp_path: Path):
    path = write_cube_stl(tmp_path / "cube.stl", 20)
    report = require_printable(path)
    assert report.ok
    assert report.stats.triangles == 12
    assert report.stats.size_mm == (20.0, 20.0, 20.0)
    assert report.stats.volume_mm3 == pytest.approx(8000.0, rel=1e-6)
    assert report.stats.manifold


def test_open_triangle_fails(tmp_path: Path):
    path = tmp_path / "tri.stl"
    path.write_text(
        "solid tri\n"
        "  facet normal 0 0 1\n"
        "    outer loop\n"
        "      vertex 0 0 0\n"
        "      vertex 1 0 0\n"
        "      vertex 0 1 0\n"
        "    endloop\n"
        "  endfacet\n"
        "endsolid tri\n",
        encoding="ascii",
    )
    report = check_mesh(path)
    assert not report.ok
    with pytest.raises(DfmError):
        require_printable(path)


def test_oversize_fails(tmp_path: Path):
    path = tmp_path / "huge.stl"
    path.write_text(ascii_stl_cube(300), encoding="ascii")
    report = check_mesh(path)
    assert not report.ok
    assert any("exceeds" in error for error in report.errors)


def test_x1c_height_limit_names_the_printer(tmp_path: Path):
    save_printer(key="x1c-0.4")
    height = machine_facts(default_profiles_dir()).bed_mm[2]
    tall = tmp_path / "tall.stl"
    tall.write_text(ascii_stl_box(20, 20, height + 2))
    report = check_mesh(tall)
    assert not report.ok and "Bambu Lab X1 Carbon" in report.errors[0]
    assert "250" in report.errors[0]
    ok = tmp_path / "ok.stl"
    ok.write_text(ascii_stl_box(20, 20, height - 1))
    assert check_mesh(ok).ok


def test_size_error_names_the_printer_of_the_profiles_checked(tmp_path: Path):
    tall = tmp_path / "tall.stl"
    tall.write_text(ascii_stl_box(20, 20, 255))  # fits the X2D (261 mm), not the X1 Carbon (250 mm)
    report = check_mesh(tall, machine=machine_facts(PACKAGE / "profiles" / "x1c-0.4"))
    assert not report.ok and "Bambu Lab X1 Carbon" in report.errors[0] and "250" in report.errors[0]
    assert check_mesh(tall).ok  # the chosen printer is still the X2D
