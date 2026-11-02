"""End-to-end tests of the YAML report written by ``pseudotest --report``."""

import pytest

from pseudotest.exceptions import ExitCode


class TestReport:
    def test_input_entry(self, ws, monkeypatch):
        monkeypatch.delenv("MPIEXEC", raising=False)
        ws.mock()
        ws.config(
            """\
            Name: Report
            Executable: mock.py
            Inputs:
              input.txt:
                Processors: 8
                Matches:
                  energy: {file: results.txt, grep: 'Energy:', field: 2, value: -42.5000}
            """
        )
        assert ws.run("--report", str(ws.report)).rc == ExitCode.OK

        report = ws.load_report()
        assert report["Name"] == "Report"
        assert report["Enabled"] is True
        assert report["Executable"] == "mock.py"
        entry = report["Inputs"]["input.txt"]
        assert entry["InputMethod"] == "argument"
        assert entry["Processors"] == 8
        assert entry["ExpectedFailure"] is False
        assert entry["Execution"] == "pass"
        assert entry["Elapsed time"] >= 0.0

    def test_match_entries(self, ws):
        """Each match lists its parameters, with the calculated value under the reference key."""
        ws.mock()
        ws.matches(
            """\
            energy: {file: results.txt, grep: 'Energy:', field: 2, value: 999.0, tol: 0.01}
            status: {file: results.txt, grep: Status, field: 2, value: converged}
            results_group:
              file: results.txt
              iterations: {grep: Iterations, field: 2, value: 10}
            files: {directory: output_dir, count_files: 2}
            multi:
              match: [m_energy, m_iterations]
              file: results.txt
              grep: ['Energy:', Iterations]
              field: 2
              value: [-42.5, 10]
            """
        )
        assert ws.run("--report", str(ws.report)).rc == ExitCode.TEST_FAILURE

        matches = ws.load_report()["Inputs"]["input.txt"]["Matches"]
        assert dict(matches["energy"]) == {
            "file": "results.txt",
            "grep": "Energy:",
            "field": 2,
            "value": -42.5,
            "reference": 999.0,
            "tol": 0.01,
            "status": "fail",
            "reason": "Difference larger than the tolerance",
        }
        assert matches["status"]["value"] == "converged"
        assert matches["status"]["reference"] == "converged"
        assert matches["status"]["status"] == "pass"
        assert "reason" not in matches["status"]
        # Groups are nested, and their parameters are listed with each match
        assert matches["results_group"]["iterations"]["file"] == "results.txt"
        assert matches["results_group"]["iterations"]["value"] == 10
        assert matches["files"]["directory"] == "output_dir"
        assert matches["files"]["count_files"] == 2
        assert matches["files"]["reference"] == 2
        # Broadcast elements are listed under their own names, without the internal 'match' key
        assert matches["m_iterations"]["value"] == 10
        assert "match" not in matches["m_energy"]

    def test_failed_extraction(self, ws):
        """A match whose value cannot be extracted has no calculated value, and the reason of the failure."""
        ws.mock()
        ws.matches(
            """\
            missing: {file: results.txt, grep: 'Not there', field: 2, value: 1.5}
            present: {directory: output_dir, file_is_present: data_a.txt}
            absent: {directory: output_dir, file_is_present: missing.txt}
            """
        )
        assert ws.run("--report", str(ws.report)).rc == ExitCode.TEST_FAILURE

        matches = ws.load_report()["Inputs"]["input.txt"]["Matches"]
        assert matches["missing"]["value"] is None
        assert matches["missing"]["reference"] == 1.5
        assert matches["missing"]["reason"] == "'Not there' not found in 'results.txt'"
        assert matches["present"]["file_is_present"] == "data_a.txt"
        assert matches["present"]["status"] == "pass"
        assert matches["absent"]["status"] == "fail"
        assert matches["absent"]["reason"] == "'missing.txt' not found in 'output_dir'"

    @pytest.mark.parametrize(
        ("expected_failure", "execution"),
        [(False, "fail"), (True, "pass")],
        ids=["unexpected", "expected"],
    )
    def test_failed_execution(self, ws, expected_failure, execution):
        """A failed execution has no matches; an expected one passes."""
        ws.mock({}, exit_code=1)
        ws.config(
            f"""\
            Name: Failed execution
            Executable: mock.py
            Inputs:
              input.txt:
                ExpectedFailure: {str(expected_failure).lower()}
                Matches:
                  missing: {{file: results.txt, grep: x, field: 1, value: 1}}
            """
        )
        ws.run("--report", str(ws.report))

        entry = ws.load_report()["Inputs"]["input.txt"]
        assert entry["ExpectedFailure"] is expected_failure
        assert entry["Execution"] == execution
        assert ("Matches" in entry) is expected_failure

    def test_disabled_test(self, ws):
        ws.config("Name: Disabled\nEnabled: false\nExecutable: missing.py\nInputs:\n  input.txt: {}\n")
        assert ws.run("--report", str(ws.report)).rc == ExitCode.OK

        report = ws.load_report()
        assert report["Enabled"] is False
        assert report["Inputs"] == {}

    def test_each_run_appends_a_document(self, ws):
        ws.mock()
        ws.matches("energy: {file: results.txt, grep: 'Energy:', field: 2, value: -42.5000}")
        ws.run("--report", str(ws.report))
        ws.run("--report", str(ws.report))

        documents = ws.load_report_documents()
        assert [list(document) for document in documents] == [[str(ws.test_file)], [str(ws.test_file)]]
        assert ws.report.read_text().count("---\n") == 2

    def test_no_report_without_option(self, ws):
        ws.mock()
        ws.matches("energy: {file: results.txt, grep: 'Energy:', field: 2, value: -42.5000}")
        ws.run()
        assert not ws.report.exists()
