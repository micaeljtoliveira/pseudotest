"""End-to-end tests of ``pseudotest-update``: tolerance (-t), reference (-r) and all-reference (-R) updates."""

from typing import Any, NamedTuple

import pytest

from pseudotest.exceptions import ExitCode

OK = ExitCode.OK
FAIL = ExitCode.TEST_FAILURE

# Outputs of the executable for all the update tests
OUTPUT = {
    "results.txt": (
        "Energy: -42.5050 Ry\n"
        "Force: 3.0000 Ha\n"
        "Overflow: ***\n"
        "Converged: false\n"
        "Short: 1.23\n"
        "Wavefunction: 1.25568286E-01\n"
    ),
    "output_dir/found.txt": "ok\n",
}

# Tolerance written for the difference of 0.005 between -42.5050 and -42.5000
TOL = 0.0055

# Marks a parameter that must not be in the updated match
ABSENT = object()


def leaf(name: str, grep: str, value: str, **params: str) -> str:
    """Return a match of the second field of the line of results.txt containing *grep*, in YAML flow style."""
    extra = "".join(f", {key}: {param}" for key, param in params.items())
    return f"{name}: {{file: results.txt, grep: '{grep}', field: 2, value: {value}{extra}}}"


ENERGY = leaf("energy", "Energy:", "-42.5000")  # fails, the output is -42.5050
ENERGY_PASSING = leaf("energy", "Energy:", "-42.5050")
ENERGY_WITHIN_TOL = leaf("energy", "Energy:", "-42.5049", tol="0.001")  # passes, but differs from the output
ENERGY_PROTECTED = leaf("energy", "Energy:", "-42.5000", protected="true")
FORCE_FAILING = leaf("force", "Force:", "99.0000")
MISSING_FILE = "missing: {directory: output_dir, file_is_present: missing_file.txt}"


def lookup(matches: Any, path: str) -> Any:
    """Return the match at *path* (match names separated by '/') in *matches*."""
    for name in path.split("/"):
        matches = matches[name]
    return matches


class Case(NamedTuple):
    mode: str
    matches: str
    rc: int
    # Expected parameters of the updated matches, by match path; None when the test file must be unchanged
    expected: dict[str, dict[str, Any]] | None


CASES = {
    # Failing matches are updated
    "tolerance-set": Case("-t", ENERGY, FAIL, {"energy": {"value": -42.5, "tol": TOL}}),
    "tolerance-increased": Case(
        "-t", leaf("energy", "Energy:", "-42.5000", tol="0.001"), FAIL, {"energy": {"value": -42.5, "tol": TOL}}
    ),
    "tolerance-below-precision-reset": Case(
        "-t", leaf("energy", "Energy:", "-42.5050", tol="0.000001"), FAIL, {"energy": {"tol": 0.0}}
    ),
    "tolerance-not-below-output-precision": Case(
        "-t", leaf("short", "Short:", "1.225"), FAIL, {"short": {"value": 1.225, "tol": 0.01}}
    ),
    "reference": Case("-r", ENERGY, FAIL, {"energy": {"value": -42.505}}),
    "reference-keeps-tolerance": Case(
        "-r", leaf("energy", "Energy:", "-42.5000", tol="0.001"), FAIL, {"energy": {"value": -42.505, "tol": 0.001}}
    ),
    "reference-all": Case("-R", ENERGY, FAIL, {"energy": {"value": -42.505}}),
    "reference-bool": Case("-r", leaf("flag", "Converged:", "true"), FAIL, {"flag": {"value": False}}),
    "reference-only-failing": Case(
        "-r", f"{ENERGY}\n{FORCE_FAILING}", FAIL, {"energy": {"value": -42.505}, "force": {"value": 3.0}}
    ),
    # Passing matches are only updated by -R
    "tolerance-passing": Case("-t", ENERGY_PASSING, OK, None),
    "reference-passing": Case("-r", ENERGY_WITHIN_TOL, OK, None),
    "reference-all-passing": Case("-R", ENERGY_WITHIN_TOL, OK, {"energy": {"value": -42.505, "tol": 0.001}}),
    # Values that cannot be extracted, or are not numbers, are not written
    "tolerance-extraction-failure": Case("-t", leaf("missing", "NONEXISTENT:", "99.0"), FAIL, None),
    "reference-extraction-failure": Case("-r", leaf("missing", "NONEXISTENT:", "99.0"), FAIL, None),
    "reference-overflow": Case("-r", leaf("overflow", "Overflow:", "1.5"), FAIL, None),
    "reference-missing-directory": Case("-r", "file_count: {directory: missing_dir, count_files: 3}", FAIL, None),
    # file_is_present is never updated
    "tolerance-file-is-present": Case(
        "-t", f"{ENERGY}\n{MISSING_FILE}", FAIL, {"energy": {"tol": TOL}, "missing": {"tol": ABSENT}}
    ),
    "reference-file-is-present": Case(
        "-r",
        f"{ENERGY}\n{MISSING_FILE}",
        FAIL,
        {"energy": {"value": -42.505}, "missing": {"file_is_present": "missing_file.txt"}},
    ),
    # Protected matches are never updated, also when they inherit protected from a group
    "tolerance-protected": Case("-t", ENERGY_PROTECTED, FAIL, None),
    "reference-protected": Case("-r", ENERGY_PROTECTED, FAIL, None),
    "reference-all-protected": Case("-R", ENERGY_PROTECTED, FAIL, None),
    "tolerance-protected-group": Case("-t", f"results:\n  protected: true\n  {ENERGY}", FAIL, None),
    "reference-protected-group": Case("-r", f"results:\n  protected: true\n  {ENERGY}", FAIL, None),
    "reference-not-protected": Case(
        "-r", leaf("energy", "Energy:", "-42.5000", protected="false"), FAIL, {"energy": {"value": -42.505}}
    ),
    "reference-protected-and-not": Case(
        "-r", f"{ENERGY_PROTECTED}\n{FORCE_FAILING}", FAIL, {"energy": {"value": -42.5}, "force": {"value": 3.0}}
    ),
    "reference-protected-group-sibling": Case(
        "-r",
        f"protected_results:\n  protected: true\n  {ENERGY}\nresults:\n  {FORCE_FAILING}",
        FAIL,
        {"protected_results/energy": {"value": -42.5}, "results/force": {"value": 3.0}},
    ),
    # Broadcast matches are updated element by element
    "tolerance-broadcast": Case(
        "-t",
        "values: {match: [energy, force], file: results.txt, grep: ['Energy:', 'Force:'], field: 2, "
        "value: [-42.5000, 3.0000]}",
        FAIL,
        {"values": {"tol": [TOL, 0]}},
    ),
    "reference-broadcast": Case(
        "-r",
        "values: {match: [energy, force], file: results.txt, grep: ['Energy:', 'Force:'], field: 2, "
        "value: [-42.5000, 3.0000]}",
        FAIL,
        {"values": {"value": [-42.505, 3.0]}},
    ),
}


class TestUpdate:
    @pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
    def test_update(self, ws, case):
        ws.mock(OUTPUT)
        ws.matches(case.matches)
        original = ws.test_file.read_text()

        assert ws.update(case.mode).rc == case.rc

        if case.expected is None:
            assert ws.test_file.read_text() == original
            return
        matches = ws.load_matches()
        for path, params in case.expected.items():
            match = lookup(matches, path)
            for key, value in params.items():
                if value is ABSENT:
                    assert key not in match
                else:
                    assert match[key] == value, f"{path}.{key}"

    @pytest.mark.parametrize(
        "case",
        [
            CASES[name]
            for name in ["tolerance-set", "tolerance-not-below-output-precision", "reference", "reference-all"]
        ]
        + [CASES["tolerance-broadcast"], CASES["reference-broadcast"]],
        ids=[
            "tolerance",
            "tolerance-precision",
            "reference",
            "reference-all",
            "tolerance-broadcast",
            "reference-broadcast",
        ],
    )
    def test_updated_test_passes(self, ws, case):
        ws.mock(OUTPUT)
        ws.matches(case.matches)
        ws.update(case.mode)
        assert ws.run().rc == OK

    @pytest.mark.parametrize("mode", ["-t", "-r", "-R"])
    def test_failed_execution_not_updated(self, ws, mode):
        ws.mock({}, exit_code=1)
        ws.matches(ENERGY)
        original = ws.test_file.read_text()
        assert ws.update(mode).rc == FAIL
        assert ws.test_file.read_text() == original

    def test_non_numeric_value_is_reported(self, ws):
        ws.mock(OUTPUT)
        ws.matches(leaf("overflow", "Overflow:", "1.5"))
        result = ws.update("-r")
        assert "Not replacing numeric reference 1.5 with non-numeric value '***'" in result.log


class TestUpdatedFile:
    """The updated test file keeps the formatting of the original."""

    MATCH = """\
        energy:
          file: results.txt
          grep: "Energy:"     # comment
          field: 2
          value: -42.5000
        """

    @pytest.mark.parametrize(("mode", "changed"), [("-r", "value: -42.5050"), ("-t", "tol: ")])
    def test_formatting_kept(self, ws, mode, changed):
        ws.mock(OUTPUT)
        ws.matches(self.MATCH)
        ws.update(mode)

        updated = ws.test_file.read_text()
        assert changed in updated
        for line in ["file: results.txt", 'grep: "Energy:"     # comment', "field: 2"]:
            assert line in updated
        if mode == "-t":
            assert "value: -42.5000" in updated

    def test_scientific_notation_kept(self, ws):
        ws.mock(OUTPUT)
        ws.matches(leaf("wavefunction", "Wavefunction:", "1.25568282E-01", tol="3.3e-09"))
        assert ws.update("-r").rc == FAIL
        assert "value: 1.25568286E-01" in ws.test_file.read_text()
        assert ws.run().rc == OK

    def test_output_to_another_file(self, ws):
        ws.mock(OUTPUT)
        ws.matches(ENERGY)
        original = ws.test_file.read_text()
        updated = ws.root / "updated.yaml"

        ws.update("-r", "--output", str(updated))

        assert ws.test_file.read_text() == original
        assert ws.load_matches(updated)["energy"]["value"] == -42.505
        assert ws.run(test_file=updated).rc == OK


class TestUpdateOptions:
    def test_report_and_preserve(self, ws):
        """pseudotest-update writes a report and keeps the working directory, as pseudotest does."""
        ws.mock(OUTPUT)
        ws.matches(ENERGY)
        result = ws.update("-r", "--report", str(ws.report), "--preserve")

        assert "Updated reference values in" in result.out
        energy = ws.load_report()["Inputs"]["input.txt"]["Matches"]["energy"]
        assert (energy["value"], energy["reference"], energy["status"]) == (-42.505, -42.5, "fail")
        assert [path.name for path in ws.work_root.iterdir()][0].startswith("pseudotest_")
