from __future__ import annotations

import hashlib
import json
import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/run-33482595275"
ARTIFACT = RUN / "artifact"
ALLOWLIST_PATH = RUN / "FXCM_CANONICAL_ALLOWLIST.json"
INVENTORY_PATH = ARTIFACT / "EXPLORATORY_FXCM_INVENTORY.json"
MANIFEST_PATH = ARTIFACT / "artifact_manifest_sha256.txt"
EXPECTED_INVENTORY_SHA256 = "353e0c6a03ea52039b9d41e3fabd6f73a41fc752bfb817c49ad0c739cca4c835"
EXPECTED_MANIFEST_SHA256 = "eebd20b64793e1d1e949f056e53e9053763e2e88ea29e7540ace2a9e5ae43398"
EXPECTED_ALLOWLIST_SHA256 = "23c8bb401a87c277e434377776769f7fba6873a1f416c9e6fe9fa4f18725b7c9"
EXPECTED_ZIP_SHA256 = "42c0f5c6d42cfd94eef1cee1c9850f91db8cd64718e2739f1083227de36705ae"
EXPECTED_SOURCE_AGGREGATE = "2f2f0386adbfd98907827213799eef797fb14bfa7aaf578c3d8a4150780560b9"
EXPECTED_OBSERVED_AGGREGATE = "4692a9085d3c132188592f2fd61c013fbe9b93e12a4e4786eed3b982da35d6f8"
EXPECTED_CROSSED_AGGREGATE = "c5e285446047735d091ad6762f01979d184b2a7fa515e28eb8fd511823ba3423"
PROHIBITED_OUTCOME_KEYS = {
    "return", "returns", "return_sign", "edge", "mfe", "mae", "win", "wins",
    "win_rate", "profit_factor", "drawdown", "cumulative_r", "p_value",
    "confidence_interval", "rank", "rankings", "outcome_chart",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_outcome_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in PROHIBITED_OUTCOME_KEYS:
                raise AssertionError(f"prohibited outcome key: {key}")
            reject_outcome_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_outcome_keys(nested)


class FxcmExploratoryCanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allowlist = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_exact_artifact_payload_and_manifest(self):
        expected = {"EXPLORATORY_FXCM_INVENTORY.json", "artifact_manifest_sha256.txt"}
        actual = set()
        for path in ARTIFACT.rglob("*"):
            self.assertFalse(path.is_symlink())
            info = path.stat(follow_symlinks=False)
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(info.st_nlink, 1)
            actual.add(path.relative_to(ARTIFACT).as_posix())
        self.assertEqual(actual, expected)
        self.assertEqual(sha256(INVENTORY_PATH), EXPECTED_INVENTORY_SHA256)
        self.assertEqual(sha256(MANIFEST_PATH), EXPECTED_MANIFEST_SHA256)
        self.assertEqual(
            MANIFEST_PATH.read_text(encoding="utf-8"),
            f"{EXPECTED_INVENTORY_SHA256}  EXPLORATORY_FXCM_INVENTORY.json\n",
        )
        self.assertNotIn("artifact_manifest_sha256.txt", MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_run_artifact_and_contract_anchors_are_exact(self):
        allowlist = self.allowlist
        self.assertEqual(sha256(ALLOWLIST_PATH), EXPECTED_ALLOWLIST_SHA256)
        self.assertEqual(set(allowlist), {
            "schema_version", "status", "freeze_date_utc", "scope", "run_identity",
            "artifact", "committed_artifact", "contract", "provider", "coverage",
            "exact_match_inventory", "canonicalization_policy", "remaining_formal_blockers",
        })
        self.assertEqual(allowlist["schema_version"], "phase9-exploratory-fxcm-canonical-allowlist-v1.0.0")
        self.assertEqual(allowlist["status"], "CANONICAL_EXPLORATORY_FX8_H1_SOURCE_QC_INVENTORY_NO_FORMAL_EFFECT")
        self.assertEqual(allowlist["freeze_date_utc"], "2026-09-01")
        self.assertEqual(allowlist["scope"], "RUN_33482595275_EXPLORATORY_FX8_H1_ONLY")
        self.assertEqual(allowlist["run_identity"], {
            "run_id": 33482595275,
            "run_number": 4,
            "run_attempt": 1,
            "head_sha": "b2eaf84e774f9ce1272344f71ac14afcb0f6849a",
            "job_id": 99775327873,
            "event": "workflow_dispatch",
            "branch": "main",
            "conclusion": "SUCCESS",
            "all_job_steps_succeeded": True,
            "working_price_cleanup": "SUCCESS",
        })
        artifact = allowlist["artifact"]
        self.assertEqual(artifact["artifact_id"], 9790552032)
        self.assertEqual(artifact["size_in_bytes"], 45454)
        self.assertEqual(artifact["github_digest"], f"sha256:{EXPECTED_ZIP_SHA256}")
        self.assertEqual(artifact["downloaded_zip_sha256"], EXPECTED_ZIP_SHA256)
        self.assertEqual(artifact["exact_file_count"], 2)
        self.assertEqual(artifact["files"], [
            {"path": INVENTORY_PATH.name, "size_in_bytes": INVENTORY_PATH.stat().st_size, "sha256": EXPECTED_INVENTORY_SHA256},
            {"path": MANIFEST_PATH.name, "size_in_bytes": MANIFEST_PATH.stat().st_size, "sha256": EXPECTED_MANIFEST_SHA256},
        ])
        self.assertTrue(artifact["zip_entries_regular_unencrypted_safe_paths"])
        self.assertTrue(artifact["manifest_check_passed"])
        self.assertFalse(artifact["manifest_self_entry_present"])
        self.assertEqual(allowlist["committed_artifact"], {
            "directory": "results/run-33482595275/artifact",
            "inventory_path": "results/run-33482595275/artifact/EXPLORATORY_FXCM_INVENTORY.json",
            "manifest_path": "results/run-33482595275/artifact/artifact_manifest_sha256.txt",
            "byte_exact_to_downloaded_artifact": True,
        })
        self.assertEqual(allowlist["contract"]["git_blob_sha"], "cfb9ff142879a59847496ed02ca307d6d9bd1540")
        self.assertEqual(allowlist["contract"]["sha256"], self.inventory["contract_sha256"])
        provider = allowlist["provider"]
        for key, value in provider.items():
            self.assertEqual(value, self.inventory["provider"][key])
        self.assertEqual(allowlist["coverage"], {
            "symbols": ["AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY", "GBPUSD", "USDJPY"],
            "timeframe": "H1",
            "start_inclusive": "2017-01-01T00:00:00Z",
            "end_exclusive": "2018-12-31T00:00:00Z",
        })

    def test_exact_832_source_inventory_and_aggregate(self):
        source = self.inventory["source_downloads"]
        provider = self.inventory["provider"]
        symbols = self.allowlist["coverage"]["symbols"]
        expected = [
            (symbol, year, week, f'{provider["base_url"]}/{symbol}/{year}/{week}.csv.gz')
            for symbol in symbols
            for year in (2017, 2018)
            for week in range(1, 53)
        ]
        actual = [(item["symbol"], item["year"], item["week"], item["url"]) for item in source]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(len(actual), 832)
        self.assertEqual(sum(item["bytes"] for item in source), 2778203)
        canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), EXPECTED_SOURCE_AGGREGATE)
        self.assertEqual(
            self.allowlist["exact_match_inventory"]["source_download_identity_aggregate_sha256"],
            EXPECTED_SOURCE_AGGREGATE,
        )

    def test_symbol_counts_hashes_and_aggregates_are_recomputable(self):
        observed = self.inventory["observed_bar_inventory"]
        for item in observed:
            expected_names = [
                f'{item["symbol"]}_{year}_{week:02d}.csv.gz'
                for year in (2017, 2018)
                for week in range(1, 53)
            ]
            rows = item["source_file_rows"]
            self.assertEqual([row["working_filename"] for row in rows], expected_names)
            self.assertEqual(sum(row["row_count"] for row in rows), item["bar_count"])
            self.assertEqual(item["usable_bar_count"] + item["crossed_open_quote_count"], item["bar_count"])
        canonical = json.dumps(
            sorted(observed, key=lambda item: (item["symbol"], item["timeframe"])),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ) + "\n"
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), EXPECTED_OBSERVED_AGGREGATE)
        crossed = hashlib.sha256()
        for item in sorted(observed, key=lambda value: value["symbol"]):
            crossed.update(
                f'{item["symbol"]}\0{item["crossed_open_quote_count"]}'
                f'\0{item["crossed_open_quote_event_sha256"]}\n'.encode("utf-8")
            )
        self.assertEqual(crossed.hexdigest(), EXPECTED_CROSSED_AGGREGATE)
        summary = self.allowlist["exact_match_inventory"]
        self.assertEqual(sum(item["bar_count"] for item in observed), summary["observed_bar_total_count"])
        self.assertEqual(sum(item["usable_bar_count"] for item in observed), summary["usable_bar_total_count"])
        self.assertEqual(sum(item["crossed_open_quote_count"] for item in observed), summary["crossed_open_quote_total_count"])
        keys = set(summary["symbols"][0]) - {"source_file_count"}
        derived = [{**{key: item[key] for key in keys}, "source_file_count": len(item["source_file_rows"])} for item in observed]
        self.assertEqual(derived, summary["symbols"])

    def test_no_formal_authorization_or_outcome_effect(self):
        policy = self.allowlist["canonicalization_policy"]
        required_false = (
            "same_run_inventory_self_authorized",
            "formal_phase9_provider_schedule_claimed",
            "formal_phase9_authorization_effect",
            "acquisition_authorized",
            "count_only_authorized",
            "full_quality_gate_passed",
            "candidate_signal_counts_calculated",
            "research_outcomes_calculated",
            "forbidden_market_period_request_attempted",
        )
        self.assertTrue(all(policy[key] is False for key in required_false))
        self.assertTrue(policy["canonicalization_commit_separate_from_run_head"])
        self.assertEqual(policy["outcome_fields"], [])
        self.assertEqual(policy["persistent_price_files"], 0)
        self.assertEqual(policy["formal_phase9_price_files_acquired"], 0)
        self.assertEqual(self.allowlist["remaining_formal_blockers"], [
            "INDEPENDENT_PROVIDER_SCHEDULE_NOT_FROZEN",
            "ENERGY_METADATA_NOT_FROZEN",
            "M15_NOT_ACQUIRED",
            "XAUUSD_NOT_ACQUIRED",
            "XAGUSD_NOT_ACQUIRED",
            "BRENT_NOT_ACQUIRED",
            "WTI_NOT_ACQUIRED",
            "JFOREX_RUNTIME_AND_REMOTE_IDENTITY_LOCK_NOT_COMPLETE",
        ])
        reject_outcome_keys(self.allowlist)
        reject_outcome_keys(self.inventory)
        for key in required_false:
            inventory_key = key if key in self.inventory else None
            if inventory_key is not None:
                self.assertIs(self.inventory[inventory_key], False)


if __name__ == "__main__":
    unittest.main()
