"""Shared mesh fixtures. The cube used to come from the package; it is only
ever a test input now that Blender owns modelling.
"""

import os
import tempfile
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Imports during collection (the MCP server's instructions) never see the real ~/print3d/printer.json."""
    os.environ["PRINT3D_PRINTER"] = str(Path(tempfile.gettempdir()) / f"print3d-tests-{os.getpid()}" / "printer.json")


def ascii_stl_box(sx: float, sy: float, sz: float) -> str:
    x, y, z = float(sx), float(sy), float(sz)
    corners = [
        (0, 0, 0), (x, 0, 0), (x, y, 0), (0, y, 0),
        (0, 0, z), (x, 0, z), (x, y, z), (0, y, z),
    ]
    faces = [
        (0, 3, 2, 1, (0, 0, -1)), (4, 5, 6, 7, (0, 0, 1)),
        (0, 1, 5, 4, (0, -1, 0)), (2, 3, 7, 6, (0, 1, 0)),
        (1, 2, 6, 5, (1, 0, 0)), (3, 0, 4, 7, (-1, 0, 0)),
    ]
    lines = ["solid box"]
    for a, b, c, d, normal in faces:
        for tri in ((a, b, c), (a, c, d)):
            lines.append("  facet normal %g %g %g" % normal)
            lines.append("    outer loop")
            lines.extend("      vertex %g %g %g" % corners[i] for i in tri)
            lines.append("    endloop")
            lines.append("  endfacet")
    lines.append("endsolid box")
    return "\n".join(lines) + "\n"


def ascii_stl_cube(size_mm: float = 20.0) -> str:
    return ascii_stl_box(size_mm, size_mm, size_mm)


def write_cube_stl(path: Path, size_mm: float = 20.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ascii_stl_cube(size_mm), encoding="ascii")
    return path


@pytest.fixture
def cube_stl(tmp_path: Path) -> Path:
    return write_cube_stl(tmp_path / "cube.stl", 20.0)


@pytest.fixture(autouse=True)
def _isolated_printer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reads the real ~/print3d/printer.json."""
    monkeypatch.setenv("PRINT3D_PRINTER", str(tmp_path / "printer.json"))
