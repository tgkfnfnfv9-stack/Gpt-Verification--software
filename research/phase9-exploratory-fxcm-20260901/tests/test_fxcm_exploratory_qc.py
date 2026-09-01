from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import sys
import tempfile
import traceback
import unittest
import urllib.error
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fxcm_qc", ROOT / "runner/fxcm_exploratory_qc.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def source(path: Path, rows: list[list[str]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(module.EXPECTED_HEADER)
        writer.writerows(rows)


def inventory_item(symbol: str, source_rows: list[dict]) -> dict:
    bar_count = sum(row["row_count"] for row in source_rows)
    return {
        "symbol": symbol,
        "timeframe": "H1",
        "timestamp_timezone": "UTC",
        "timestamp_semantics": "ROW_TIMESTAMP_ASSUMED_BAR_OPEN_NOT_PROVIDER_EXPLICIT",
        "observed_timestamps_working_filename": f"{symbol}_H1.timestamps.txt",
        "observed_timestamps_sha256": module.EMPTY_SHA256,
        "usable_timestamps_sha256": module.EMPTY_SHA256,
        "usable_bid_working_sha256": module.EMPTY_SHA256,
        "usable_ask_working_sha256": module.EMPTY_SHA256,
        "bar_count": bar_count,
        "usable_bar_count": bar_count,
        "crossed_open_quote_count": 0,
        "crossed_open_quote_event_sha256": module.EMPTY_SHA256,
        "first_timestamp_utc": "2017-01-01T00:00:00Z" if bar_count else None,
        "last_timestamp_utc": "2018-12-30T23:00:00Z" if bar_count else None,
        "gap_segment_count": 0,
        "missing_hour_slot_count": 0,
        "usable_gap_segment_count": 0,
        "usable_missing_hour_slot_count": 0,
        "source_file_rows": source_rows,
        "trailing_hours_to_contract_end": 1,
    }


class FxcmQCTests(unittest.TestCase):
    def test_frozen_contract(self):
        value = module.load_contract(ROOT / "spec/fxcm_exploratory_contract.frozen.json")
        self.assertEqual(len(value["symbols"]), 8)
        self.assertFalse(value["formal_authorization_effect"])
        self.assertEqual(value["provider"], module.EXPECTED_PROVIDER)
        self.assertEqual(value["usage_constraints"], module.EXPECTED_USAGE)
        self.assertEqual(value["crossed_open_quote_policy"], module.EXPECTED_CROSSED_OPEN_POLICY)
        self.assertEqual(value["status"], "FROZEN_BEFORE_RETRY_AFTER_FAILED_PRICE_ACCESS")

    def test_bid_ask_integrity_and_gap_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gz = root / "one.csv.gz"
            source(gz, [
                ["01/01/2017 00:00:00.000", "1", "1.2", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
                ["01/01/2017 02:00:00.000", "1.1", "1.3", "1", "1.2", "1.11", "1.31", "1.01", "1.21"],
            ])
            prices = root / "prices"; prices.mkdir()
            observed = root / "observed"; observed.mkdir()
            item = module.process_symbol("EURUSD", [gz], prices, observed)
            self.assertEqual(item["bar_count"], 2)
            self.assertEqual(item["usable_bar_count"], 2)
            self.assertEqual(item["crossed_open_quote_count"], 0)
            self.assertEqual(item["crossed_open_quote_event_sha256"], module.EMPTY_SHA256)
            self.assertEqual(item["timestamp_timezone"], "UTC")
            self.assertEqual(item["timestamp_semantics"], "ROW_TIMESTAMP_ASSUMED_BAR_OPEN_NOT_PROVIDER_EXPLICIT")
            self.assertEqual(item["gap_segment_count"], 1)
            self.assertEqual(item["missing_hour_slot_count"], 1)
            self.assertEqual(item["usable_gap_segment_count"], 1)
            self.assertEqual(item["usable_missing_hour_slot_count"], 1)

    def test_crossed_open_is_quarantined_and_aggregate_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gz = root / "one.csv.gz"
            source(gz, [
                ["01/01/2017 00:00:00.000", "1", "1.2", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
                ["01/01/2017 01:00:00.000", "1", "1.2", "0.9", "1.1", "0.99", "1.21", "0.91", "1.11"],
                ["01/01/2017 02:00:00.000", "1", "1.2", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
            ])
            prices = root / "prices"; prices.mkdir()
            observed = root / "observed"; observed.mkdir()
            item = module.process_symbol("EURUSD", [gz], prices, observed)
            self.assertEqual(item["bar_count"], 3)
            self.assertEqual(item["usable_bar_count"], 2)
            self.assertEqual(item["crossed_open_quote_count"], 1)
            self.assertNotEqual(item["crossed_open_quote_event_sha256"], module.EMPTY_SHA256)
            self.assertEqual(item["gap_segment_count"], 0)
            self.assertEqual(item["usable_gap_segment_count"], 1)
            self.assertEqual(item["usable_missing_hour_slot_count"], 1)
            self.assertEqual(len((prices / "EURUSD_H1_bid.csv").read_text().splitlines()), 3)
            self.assertEqual(len((prices / "EURUSD_H1_ask.csv").read_text().splitlines()), 3)
            self.assertEqual(len((observed / "EURUSD_H1.timestamps.txt").read_text().splitlines()), 3)
            with_cross = module.inventory_aggregate_sha([{**item, "trailing_hours_to_contract_end": 1}])
            without_cross = module.inventory_aggregate_sha([{
                **item,
                "usable_bar_count": 3,
                "crossed_open_quote_count": 0,
                "crossed_open_quote_event_sha256": module.EMPTY_SHA256,
                "trailing_hours_to_contract_end": 1,
            }])
            self.assertNotEqual(with_cross, without_cross)

    def test_bad_geometry_nonpositive_and_forbidden_time_fail(self):
        rows = [
            ["01/01/2017 00:00:00.000", "1", "0.8", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
            ["01/01/2017 00:00:00.000", "0", "1.2", "0", "1.1", "1.01", "1.21", "0.91", "1.11"],
            ["12/31/2016 23:00:00.000", "1", "1.2", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
            ["12/31/2018 00:00:00.000", "1", "1.2", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
            ["01/01/2017 00:01:00.000", "1", "1.2", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
        ]
        for row in rows:
            with self.subTest(row=row), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); gz = root / "bad.csv.gz"; source(gz, [row])
                (root / "prices").mkdir(); (root / "observed").mkdir()
                with self.assertRaises(module.FxcmError):
                    module.process_symbol("EURUSD", [gz], root / "prices", root / "observed")

    def test_parse_errors_do_not_echo_raw_values(self):
        timestamp_sentinel = "SECRET_" + "TIMESTAMP_SENTINEL"
        price_sentinel = "SECRET_" + "PRICE_SENTINEL"
        price_parser = lambda text: module.parse_price(text, "BidOpen")
        for value, parser in (
            (timestamp_sentinel, module.parse_timestamp),
            (price_sentinel, price_parser),
        ):
            with self.subTest(value=value):
                try:
                    parser(value)
                except module.FxcmError:
                    rendered = "".join(traceback.format_exception(*sys.exc_info()))
                else:
                    self.fail("parser accepted invalid sentinel")
                self.assertNotIn(value, rendered)

    def test_bad_header_does_not_echo_market_values(self):
        timestamp_sentinel = "SECRET_" + "HEADER_TIMESTAMP"
        price_sentinel = "SECRET_" + "HEADER_PRICE"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gz = root / "bad.csv.gz"
            with gzip.open(gz, "wt", encoding="utf-8", newline="") as handle:
                csv.writer(handle).writerow([timestamp_sentinel, *([price_sentinel] * 8)])
            (root / "prices").mkdir(); (root / "observed").mkdir()
            try:
                module.process_symbol("EURUSD", [gz], root / "prices", root / "observed")
            except module.FxcmError:
                rendered = "".join(traceback.format_exception(*sys.exc_info()))
            else:
                self.fail("invalid header was accepted")
            self.assertNotIn(timestamp_sentinel, rendered)
            self.assertNotIn(price_sentinel, rendered)

    def test_transient_download_retries_remove_partial_file_and_stay_bounded(self):
        payload = gzip.compress(b"bounded retry fixture" * 4)

        class Response:
            status = 200

            def __init__(self, chunks):
                self.chunks = iter(chunks)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                value = next(self.chunks, b"")
                if isinstance(value, BaseException):
                    raise value
                return value

        class Opener:
            def __init__(self, responses):
                self.responses = iter(responses)
                self.calls = 0

            def open(self, _request, timeout):
                self.calls += 1
                self.assert_timeout = timeout
                value = next(self.responses)
                if isinstance(value, BaseException):
                    raise value
                return value

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module.time, "sleep") as sleep:
            destination = Path(directory) / "fixture.csv.gz"
            opener = Opener([
                Response([payload[:12], ConnectionResetError("reset")]),
                urllib.error.URLError(ConnectionResetError("reset")),
                Response([payload]),
            ])
            result = module.download("https://example.invalid/frozen.csv.gz", destination, opener)
            self.assertEqual(opener.calls, 3)
            self.assertEqual(opener.assert_timeout, 60)
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(result["sha256"], module.sha256_file(destination))
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.0, 2.0])

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module.time, "sleep") as sleep:
            destination = Path(directory) / "fixture.csv.gz"
            opener = Opener([
                urllib.error.URLError(ConnectionResetError("reset"))
                for _ in range(module.DOWNLOAD_MAX_ATTEMPTS)
            ])
            with self.assertRaisesRegex(module.FxcmError, "after 4 attempts"):
                module.download("https://example.invalid/frozen.csv.gz", destination, opener)
            self.assertEqual(opener.calls, module.DOWNLOAD_MAX_ATTEMPTS)
            self.assertFalse(destination.exists())
            self.assertEqual(
                [call.args[0] for call in sleep.call_args_list],
                list(module.DOWNLOAD_RETRY_DELAYS_SECONDS),
            )

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module.time, "sleep") as sleep:
            destination = Path(directory) / "fixture.csv.gz"
            url = "https://example.invalid/frozen.csv.gz"
            opener = Opener([urllib.error.HTTPError(url, 503, "unavailable", {}, None)])
            with self.assertRaisesRegex(module.FxcmError, "unexpected status 503"):
                module.download(url, destination, opener)
            self.assertEqual(opener.calls, 1)
            self.assertFalse(destination.exists())
            sleep.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "fixture.csv.gz"
            destination.write_bytes(b"preexisting")
            opener = Opener([Response([payload])])
            with self.assertRaises(FileExistsError):
                module.download("https://example.invalid/frozen.csv.gz", destination, opener)
            self.assertEqual(destination.read_bytes(), b"preexisting")
            self.assertEqual(opener.calls, 0)

    def test_outcome_fields_rejected(self):
        module.reject_outcomes({"bar_count": 1, "crossed_open_quote_count": 1})
        literal_prohibited = (
            "return", "returns", "return_sign", "edge", "mfe", "mae", "win", "wins",
            "win_rate", "profit_factor", "drawdown", "cumulative_r", "p_value",
            "confidence_interval", "rank", "rankings", "outcome_chart",
        )
        for field in literal_prohibited:
            with self.subTest(field=field), self.assertRaises(module.FxcmError):
                module.reject_outcomes({field: 0})

    def test_inventory_shape_rejects_extra_anomaly_detail(self):
        required = inventory_item("EURUSD", [])
        module.validate_inventory_shape([required])
        for forbidden in ("event_timestamps", "event_prices", "spread", "difference", "magnitude"):
            with self.subTest(forbidden=forbidden), self.assertRaises(module.FxcmError):
                module.validate_inventory_shape([{**required, forbidden: []}])

    def test_canonical_inventory_aggregate_is_recomputable(self):
        inventory = [
            {"symbol": "EURUSD", "timeframe": "H1", "crossed_open_quote_count": 1},
            {"symbol": "AUDUSD", "timeframe": "H1", "crossed_open_quote_count": 0},
        ]
        self.assertEqual(module.inventory_aggregate_sha(inventory), module.inventory_aggregate_sha(list(reversed(inventory))))
        canonical = json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        sorted_canonical = json.dumps(sorted(inventory, key=lambda item: (item["symbol"], item["timeframe"])), sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        self.assertNotEqual(canonical, sorted_canonical)
        self.assertEqual(module.inventory_aggregate_sha(inventory), module.hashlib.sha256(sorted_canonical.encode()).hexdigest())
        mutated = [{**inventory[0], "crossed_open_quote_count": 2}, inventory[1]]
        self.assertNotEqual(module.inventory_aggregate_sha(inventory), module.inventory_aggregate_sha(mutated))

    def test_exact_symbol_and_source_inventory(self):
        contract = module.load_contract(ROOT / "spec/fxcm_exploratory_contract.frozen.json")
        inventories = []
        for symbol in contract["symbols"]:
            rows = [
                {"working_filename": f"{symbol}_{year}_{week:02d}.csv.gz", "row_count": 1}
                for year in contract["years"]
                for week in range(1, contract["weeks_per_year"] + 1)
            ]
            inventories.append(inventory_item(symbol, rows))
        module.validate_inventory_shape(inventories, contract)
        with self.assertRaises(module.FxcmError):
            module.validate_inventory_shape(list(reversed(inventories)), contract)
        broken = [{**inventories[0], "source_file_rows": inventories[0]["source_file_rows"][:-1]}, *inventories[1:]]
        with self.assertRaises(module.FxcmError):
            module.validate_inventory_shape(broken, contract)

    def test_report_shape_and_report_tree_are_exact(self):
        report = {key: None for key in module.REPORT_KEYS}
        for field in (
            "acquisition_authorized", "count_only_authorized",
            "provider_schedule_inventory_claimed", "provider_schedule_gate_passed",
            "full_quality_gate_passed", "candidate_signal_counts_calculated",
            "research_outcomes_calculated", "forbidden_market_period_request_attempted",
        ):
            report[field] = False
        report["outcome_fields"] = []
        module.validate_report_shape(report)
        with self.assertRaises(module.FxcmError):
            module.validate_report_shape({**report, "event_prices": []})
        with self.assertRaises(module.FxcmError):
            module.validate_report_shape({**report, "count_only_authorized": True})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "EXPLORATORY_FXCM_INVENTORY.json"
            inventory.write_text("{}\n")
            module.validate_report_tree(root, {}, False)
            extra = root / "rawdata"
            extra.write_text("forbidden\n")
            with self.assertRaises(module.FxcmError):
                module.validate_report_tree(root, {}, False)
            extra.unlink()
            link = root / "linked"
            link.symlink_to(inventory)
            with self.assertRaises(module.FxcmError):
                module.validate_report_tree(root, {}, False)

    def test_manifest_seals_payload_only_without_false_self_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "EXPLORATORY_FXCM_INVENTORY.json"
            inventory.write_text("{}\n", encoding="utf-8")
            module.seal_manifest(root, {})
            manifest = root / "artifact_manifest_sha256.txt"
            self.assertEqual(
                manifest.read_text(encoding="utf-8"),
                f"{module.sha256_file(inventory)}  {inventory.name}\n",
            )
            self.assertNotIn(manifest.name, manifest.read_text(encoding="utf-8"))
            self.assertNotEqual(module.sha256_file(manifest), module.EMPTY_SHA256)
            module.validate_report_tree(root, {}, True)

    def test_workflow_is_manual_only(self):
        workflow = (ROOT.parents[1] / ".github/workflows/phase9-exploratory-fxcm-qc.yml").read_text()
        trigger_block = workflow.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
        trigger_keys = [line.strip()[:-1] for line in trigger_block.splitlines() if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":" )]
        self.assertEqual(trigger_keys, ["workflow_dispatch"])
        self.assertIn(module.CONFIRMATION, workflow)
        self.assertIn(module.USAGE_CONFIRMATION, workflow)


if __name__ == "__main__":
    unittest.main()
