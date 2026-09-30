import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from herdr_runtime.contracts import (  # noqa: E402
    ContractError, event_id, read_result_file, validate_assignment, validate_capability,
    validate_event, validate_member, validate_metric, validate_result,
    validate_result_binding, validate_run,
)


def example(name):
    return json.loads((ROOT / "templates" / f"{name}.example.json").read_text())


class ContractTests(unittest.TestCase):
    def test_templates_are_valid_and_bound(self):
        run, assignment, result = (example(name) for name in ("run", "assignment", "result"))
        validate_run(run)
        validate_member(run["members"][0])
        validate_assignment(assignment)
        validate_result(result)
        validate_result_binding(result, assignment)
        handoff = example("handoff")
        validate_result_binding(handoff, assignment)

    def test_unknown_schema_and_field_errors(self):
        run = example("run")
        run["schema_version"] = 2
        with self.assertRaisesRegex(ContractError, "schema_version"):
            validate_run(run)
        result = example("result")
        result["verification"] = [{"check": "test", "cwd": ".", "result": "OK", "evidence": None}]
        with self.assertRaisesRegex(ContractError, "verification\\[0\\].result"):
            validate_result(result)

    def test_wrong_identity_and_stale_revision(self):
        result = example("result")
        assignment = example("assignment")
        for key, value in (("assignment_id", "other"), ("conversation_id", "other"), ("revision", 1), ("attempt", 2)):
            changed = copy.deepcopy(result)
            changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ContractError, key):
                validate_result_binding(changed, assignment)

    def test_result_paths_and_empty_summary(self):
        for path in ("../other", "/private/file", "a/../../b", "a\\b"):
            result = example("result")
            result["files_changed"] = [path]
            with self.subTest(path=path), self.assertRaisesRegex(ContractError, "files_changed"):
                validate_result(result)
        result = example("result")
        result["summary"] = " "
        with self.assertRaisesRegex(ContractError, "summary"):
            validate_result(result)

    def test_handoff_is_data_and_direct_route_requires_exact_grant(self):
        assignment = example("assignment")
        result = example("result")
        result["next_handoff"] = {"route": "owner", "target_member_id": "reviewer",
                                  "instruction": "Review the findings", "evidence": [
                                      {"path": "evidence/report.md", "sha256": "a" * 64}]}
        validate_result_binding(result, assignment)
        result["next_handoff"]["route"] = "direct"
        with self.assertRaisesRegex(ContractError, "owner grant"):
            validate_result_binding(result, assignment)
        assignment["route_grant"] = {"grant_id": "g1", "route": "direct",
                                     "target_member_id": "reviewer", "max_hops": 1}
        validate_result_binding(result, assignment)
        result["next_handoff"]["command"] = "herdr agent start surprise"
        with self.assertRaisesRegex(ContractError, "unsupported field"):
            validate_result(result)
        self.assertEqual(assignment["route_grant"]["target_member_id"], "reviewer")

    def test_scope_and_parallelism(self):
        run = example("run")
        run["members"][0]["tab_id"] = "other-tab"
        with self.assertRaisesRegex(ContractError, "outside run scope"):
            validate_run(run)
        run = example("run")
        run["execution_mode"] = "parallel"
        with self.assertRaisesRegex(ContractError, "parallel not authorized"):
            validate_run(run)

    def test_real_herdr_ids_and_alias_rules(self):
        run = example("run")
        self.assertEqual(validate_run(run)["scope"]["owner_pane_id"], "w1:p1")
        run["members"][0]["agent_alias"] = "Worker 1"
        with self.assertRaisesRegex(ContractError, "agent_alias"):
            validate_run(run)

    def test_quota_unknown_is_not_zero(self):
        metric = {"state": "unknown", "value": None, "unit": "USD", "scope": "account", "observed_at": "2026-09-29T00:00:00Z", "source": "native"}
        validate_metric(metric)
        metric["value"] = 0
        with self.assertRaisesRegex(ContractError, "value"):
            validate_metric(metric)

    def test_capability_and_epoch_independent_event_id(self):
        validate_capability({"status": "unknown", "method": "native", "version": "0.9.2", "observation": "not tested"})
        event = {"schema_version": 1, "run_id": "example-run", "assignment_id": "example-assignment", "revision": 0, "attempt": 1, "type": "result", "result_digest": "a" * 64, "owner_epoch": 1}
        validate_event(event)
        first = event_id(event)
        event["owner_epoch"] = 2
        self.assertEqual(first, event_id(event))

    def test_result_file_rejects_truncation_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "result.json"
            result.write_text(json.dumps(example("result")))
            self.assertEqual(read_result_file(root, "result.json")["status"], "done")
            result.write_text("{\"schema_version\":1")
            with self.assertRaisesRegex(ContractError, "invalid UTF-8 JSON"):
                read_result_file(root, "result.json")
            result.write_bytes(b"x" * (12 * 1024 + 1))
            with self.assertRaisesRegex(ContractError, "bounded regular file"):
                read_result_file(root, "result.json")
            result.unlink()
            result.symlink_to(root / "target")
            with self.assertRaisesRegex(ContractError, "unsafe or unreadable"):
                read_result_file(root, "result.json")
            with self.assertRaisesRegex(ContractError, "result_path"):
                read_result_file(root, "../outside")


if __name__ == "__main__":
    unittest.main()
