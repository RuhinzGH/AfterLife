"""The assumptions table (S2-12) covers every scoring constant, and its values
come from the code, not from typing."""
import ast
import importlib
import inspect
import numbers

from fastapi.testclient import TestClient

from afterlife import assumptions as A
from afterlife import assessment, grid
from api.main import app


def _has_number(v, depth=0):
    if isinstance(v, bool) or depth > 4:
        return False
    if isinstance(v, numbers.Number):
        return True
    if isinstance(v, dict):
        return any(_has_number(x, depth + 1) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_has_number(x, depth + 1) for x in v)
    return False


def _assigned_here(mod):
    """Names a module assigns itself at top level (not ones it imports)."""
    names = set()
    for node in ast.parse(inspect.getsource(mod)).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    names.add(n.id)
    return names


def _constants(module, prefixes=None):
    mod = importlib.import_module(module)
    for name in sorted(_assigned_here(mod)):
        if not name.lstrip("_").isupper() or name.startswith("__"):
            continue
        if prefixes and not name.startswith(prefixes):
            continue
        if _has_number(getattr(mod, name, None)):
            yield f"{module}:{name}"


def test_every_numeric_constant_in_the_audited_modules_has_a_row():
    rows = {r["ref"] for g in A.GROUPS for r in g["rows"] if isinstance(r["ref"], str)}
    found = [c for m in A.AUDITED_MODULES for c in _constants(m)]
    found += [c for m, pre in A.AUDITED_PREFIXES.items() for c in _constants(m, pre)]
    missing = [c for c in found if c not in rows and c not in A.NOT_ASSUMPTIONS]
    assert not missing, f"constants with no row in the assumptions table: {missing}"


def test_the_coverage_check_would_catch_a_new_constant(tmp_path, monkeypatch):
    (tmp_path / "fake_rules.py").write_text(
        "from afterlife.assessment import EOL_WEIGHT\nNEW_PENALTY = -7\nLABEL = 'text'\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    # the new number is found; the borrowed one and the text label are not
    assert list(_constants("fake_rules")) == ["fake_rules:NEW_PENALTY"]


def test_every_row_points_at_something_that_exists():
    for g in A.GROUPS:
        for r in g["rows"]:
            assert A._value(r["ref"]) is not None, r["name"]


def test_values_come_from_the_code():
    rows = {r["name"]: r for g in A.table()["groups"] for r in g["rows"]}
    assert rows["Points for a 100% end-of-life risk"]["value"] == str(assessment.EOL_WEIGHT)
    assert rows["Hours a day: light, typical, heavy"]["value"] == " · ".join(
        f"{k} {v}" for k, v in grid.SCENARIO_HOURS.items())


def test_every_row_has_a_kind_reason_limit_and_source():
    for g in A.table()["groups"]:
        for r in g["rows"]:
            assert r["kind"] in (A.LEARNED, A.LOOKED_UP, A.CHOSEN)
            assert r["why"] and r["limit"] and r["source"], r["name"]


def test_endpoint():
    d = TestClient(app).get("/api/assumptions").json()
    assert len(d["groups"]) >= 6 and sum(d["counts"].values()) > 40
