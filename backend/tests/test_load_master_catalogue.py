"""Validation for supabase/seed/load_master_catalogue.py's row-mapping logic (PR #10 review
finding: openpyxl was an undeclared dependency with zero test coverage). The script is standalone
tooling outside the `app` package, so it's loaded by file path rather than imported normally.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from types import ModuleType

import openpyxl
import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "supabase" / "seed" / "load_master_catalogue.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("load_master_catalogue", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_module = _load_module()


def _row(
    diet: str = "Vegetarian",
    family: str | None = "Poriyal",
    name: str = "Test Dish",
    region: str | None = "Tamil Nadu",
) -> tuple:
    # Column layout matches the real workbook's "Master Dishes" sheet, per
    # load_master_catalogue.py's _load_candidates: Diet at index 2, Dish Family at index 3, Name
    # at index 5, Region Style at index 9.
    return (None, None, diet, family, None, name, None, None, None, region)


def _workbook(rows: list[tuple]) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Master Dishes"
    ws.append([f"col{i}" for i in range(10)])  # header row — _load_candidates starts at row 2
    for row in rows:
        ws.append(row)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    return path


@pytest.fixture
def load_candidates():
    return _module._load_candidates


def test_a_known_family_maps_to_its_item_type(load_candidates) -> None:
    path = _workbook([_row(family="Kuzhambu", name="Sample Kuzhambu")])

    assert load_candidates(path) == [("Sample Kuzhambu", "gravy", "veg", "Tamil Nadu")]


def test_a_condiment_only_family_is_skipped(load_candidates) -> None:
    for family in ("Chutney", "Accompaniment", "Thuvaiyal", "Pachadi", "Masiyal/Gothsu"):
        path = _workbook([_row(family=family, name=f"{family} sample")])
        assert load_candidates(path) == []


def test_an_unrecognized_family_is_skipped(load_candidates) -> None:
    path = _workbook([_row(family="Not A Real Family")])

    assert load_candidates(path) == []


def test_egg_diet_maps_to_nonveg(load_candidates) -> None:
    path = _workbook([_row(diet="Egg", name="Egg Curry")])

    candidates = load_candidates(path)
    assert candidates == [("Egg Curry", "poriyal", "nonveg", "Tamil Nadu")]


def test_an_unrecognized_diet_is_skipped(load_candidates) -> None:
    path = _workbook([_row(diet="Vegan")])

    assert load_candidates(path) == []


def test_a_row_with_no_name_is_skipped(load_candidates) -> None:
    path = _workbook([_row(name="")])

    assert load_candidates(path) == []


def test_region_style_is_optional(load_candidates) -> None:
    path = _workbook([_row(region=None)])

    candidates = load_candidates(path)
    assert candidates[0][3] is None


def test_the_header_row_is_never_treated_as_data(load_candidates) -> None:
    path = _workbook([])  # no data rows beyond the header

    assert load_candidates(path) == []
