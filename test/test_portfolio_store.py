"""Tests for local SQLite portfolio persistence."""

from datetime import datetime
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"),
)

from modules.portfolio_store import PortfolioStore


class PortfolioStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = PortfolioStore(
            os.path.join(self.temp_dir.name, "portfolio.sqlite3")
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_replaces_and_restores_records(self):
        self.store.replace_many(
            {"mf_trades": [{"Txn_Date": datetime(2025, 1, 2), "Quantity": 3.5}]}
        )

        self.assertEqual(
            self.store.load("mf_trades"),
            [{"Txn_Date": "2025-01-02T00:00:00", "Quantity": 3.5}],
        )
        self.store.replace_many({"mf_trades": []})
        self.assertEqual(self.store.load("mf_trades"), [])

    def test_failed_batch_rolls_back_collection_replacement(self):
        self.store.replace_many({"stocks": [{"Symbol": "KEEP"}]})
        batch = {
            "batch_id": "duplicate-id",
            "asset_type": "stocks",
            "original_filename": "stocks.xlsx",
            "stored_filename": "unique_stocks.xlsx",
            "imported_at": "2025-01-01T00:00:00",
            "record_count": 1,
        }
        self.store.replace_many({"stocks": [{"Symbol": "FIRST"}]}, batch)

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.replace_many({"stocks": [{"Symbol": "MUST_ROLL_BACK"}]}, batch)

        self.assertEqual(self.store.load("stocks"), [{"Symbol": "FIRST"}])

    def test_pan_scopes_records_and_first_investor_claims_legacy_data(self):
        self.store.replace_many({"property_assets": [{"name": "Legacy"}]})
        self.store.create_investor("abcde1234f", "Investor One")
        self.assertEqual(
            self.store.load("property_assets"), [{"name": "Legacy"}]
        )

        self.store.replace_many({"property_assets": [{"name": "One"}]})
        self.store.create_investor("FGHIJ5678K", "Investor Two")
        self.store.replace_many(
            {"property_assets": [{"name": "Two"}]},
            investor_pan="FGHIJ5678K",
        )

        self.assertEqual(
            self.store.load("property_assets", "ABCDE1234F"), [{"name": "One"}]
        )
        self.assertEqual(
            self.store.load("property_assets", "FGHIJ5678K"), [{"name": "Two"}]
        )

    def test_pan_is_unique_case_insensitively(self):
        self.store.create_investor("abcde1234f", "Investor One")

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_investor("ABCDE1234F", "Duplicate")


if __name__ == "__main__":
    unittest.main()
