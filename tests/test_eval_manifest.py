import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EvalManifestTests(unittest.TestCase):
    def test_realistic_scenarios_have_trace_and_unrun_status(self):
        manifest = json.loads((ROOT / "evals" / "scenarios.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        scenarios = manifest["scenarios"]
        self.assertEqual([item["id"] for item in scenarios], [f"U{index:02d}" for index in range(1, 11)])
        for item in scenarios:
            self.assertEqual(item["status"], "NOT_RUN")
            for key in ("user_prompt", "preconditions", "allowed_trace", "forbidden_trace", "rubric"):
                self.assertTrue(item[key], (item["id"], key))

    def test_coverage_report_names_each_case_without_claiming_full_pass(self):
        report = (ROOT / "evals" / "coverage.md").read_text()
        cases = re.findall(r"(?m)^\| (X\d{2}) \|", report)
        self.assertEqual(cases, [f"X{index:02d}" for index in range(1, 57)])
        requirements = re.findall(r"(?m)^\| (R\d{2}) \|", report)
        self.assertEqual(requirements, [f"R{index:02d}" for index in range(1, 19)])
        self.assertIn("`events_lost` re-subscription absent", report)


if __name__ == "__main__":
    unittest.main()
