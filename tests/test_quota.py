import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from herdr_runtime.quota import (cache_sample, check_choice, read_quota,
                                 unknown_sample, validate_catalog)  # noqa: E402
from herdr_runtime.state import StateStore  # noqa: E402


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StateStore(self.root / "state")
        catalog = json.loads((ROOT / "templates" / "model-catalog.example.json").read_text())
        self.profile = validate_catalog(catalog)[0]
        self.profile["authorized"] = True
        self.now = datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc)

    def test_unknown_session_and_balance_are_distinct(self):
        sample = unknown_sample(self.profile, self.now)
        self.assertEqual(sample["metrics"]["session_usage"]["scope"], "session")
        self.assertEqual(sample["metrics"]["api_balance"]["scope"], "API account")
        for metric in sample["metrics"].values():
            self.assertEqual(metric["state"], "unknown")
            self.assertIsNone(metric["value"])

    def test_cache_ttl_and_account_change(self):
        sample = unknown_sample(self.profile, self.now)
        sample["reader"] = "offline-fixture"
        sample["metrics"]["session_usage"].update(state="known", value=200, unit="tokens",
                                                    source="offline session fixture")
        cache_sample(self.profile, sample, self.store)
        current = read_quota(self.profile, self.store, now=self.now + timedelta(seconds=299))
        self.assertEqual(current["cache"], "fresh")
        self.assertEqual(current["sample"]["metrics"]["session_usage"]["value"], 200)
        stale = read_quota(self.profile, self.store, now=self.now + timedelta(seconds=301))
        self.assertEqual(stale["cache"], "stale")
        self.assertEqual(stale["sample"]["metrics"]["session_usage"]["state"], "stale")
        self.assertIsNone(stale["sample"]["metrics"]["session_usage"]["value"])
        other = copy.deepcopy(self.profile)
        other["account_ref"] = "other-account"
        self.assertEqual(read_quota(other, self.store, now=self.now)["cache"], "miss")

    def test_selected_profile_never_silently_changes(self):
        sample = unknown_sample(self.profile, self.now)
        explicit = check_choice(self.profile, sample, mode="explicit")
        self.assertEqual(explicit["profile_id"], self.profile["profile_id"])
        self.assertEqual(explicit["outcome"], "eligible_with_uncertainty")
        self.assertIn("api_balance", explicit["unknown"])
        self.assertEqual(check_choice(self.profile, sample, mode="auto_authorized")["outcome"], "needs_info")
        self.profile["authorized"] = False
        self.assertEqual(check_choice(self.profile, sample, mode="explicit")["outcome"], "blocked")

    def test_quota_cli_is_passive_outside_herdr(self):
        catalog = self.root / "catalog.json"
        catalog.write_text((ROOT / "templates" / "model-catalog.example.json").read_text())
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "herdr_orchestrate.py"),
                                 "quota", "read", "--catalog", str(catalog),
                                 "--profile-id", "example-profile", "--state-dir", str(self.root / "private")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        body = json.loads(result.stdout)
        self.assertEqual(body["sample"]["metrics"]["api_balance"]["state"], "unknown")
        self.assertEqual(body["cache"], "miss")


if __name__ == "__main__":
    unittest.main()
