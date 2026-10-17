"""SQLite persistence for the local portfolio."""

from datetime import date, datetime
from contextlib import contextmanager
import json
import math
import os
import re
import sqlite3


class PortfolioStore:
    """Store ordered portfolio record collections in a local SQLite file."""

    def __init__(self, database_path: str):
        self.database_path = database_path
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolio_records (
                    collection TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (collection, position)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS upload_batches (
                    batch_id TEXT PRIMARY KEY,
                    investor_pan TEXT NOT NULL DEFAULT '',
                    asset_type TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    record_count INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS investors (
                    pan TEXT PRIMARY KEY COLLATE NOCASE,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            batch_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(upload_batches)")
            }
            if "investor_pan" not in batch_columns:
                connection.execute(
                    "ALTER TABLE upload_batches ADD COLUMN investor_pan TEXT NOT NULL DEFAULT ''"
                )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _json_value(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if hasattr(value, "item"):
            return PortfolioStore._json_value(value.item())
        if isinstance(value, float) and not math.isfinite(value):
            return None
        raise TypeError(f"Cannot store value of type {type(value).__name__}")

    @staticmethod
    def _scoped_collection(collection: str, investor_pan: str | None) -> str:
        return f"{investor_pan.upper()}::{collection}" if investor_pan else collection

    def _effective_pan(self, investor_pan: str | None) -> str | None:
        if investor_pan is not None:
            return investor_pan.strip().upper()
        investor = self.get_active_investor()
        return investor["pan"] if investor else None

    def load(self, collection: str, investor_pan: str | None = None) -> list[dict]:
        investor_pan = self._effective_pan(investor_pan)
        collection = self._scoped_collection(collection, investor_pan)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM portfolio_records WHERE collection = ? ORDER BY position",
                (collection,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def replace_many(
        self,
        collections: dict[str, list[dict]],
        import_batch: dict | None = None,
        investor_pan: str | None = None,
    ) -> None:
        """Atomically replace one or more complete collections."""
        investor_pan = self._effective_pan(investor_pan)
        scoped_collections = {
            self._scoped_collection(name, investor_pan): records
            for name, records in collections.items()
        }
        encoded = {
            name: [
                json.dumps(record, default=self._json_value, allow_nan=False)
                for record in records
            ]
            for name, records in scoped_collections.items()
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for collection, records in encoded.items():
                connection.execute(
                    "DELETE FROM portfolio_records WHERE collection = ?", (collection,)
                )
                connection.executemany(
                    """INSERT INTO portfolio_records (collection, position, payload)
                       VALUES (?, ?, ?)""",
                    [
                        (collection, position, payload)
                        for position, payload in enumerate(records)
                    ],
                )
            if import_batch is not None:
                connection.execute(
                    """INSERT INTO upload_batches
                       (batch_id, investor_pan, asset_type, original_filename, stored_filename,
                        imported_at, record_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        import_batch["batch_id"],
                        investor_pan or "",
                        import_batch["asset_type"],
                        import_batch["original_filename"],
                        import_batch["stored_filename"],
                        import_batch["imported_at"],
                        import_batch["record_count"],
                    ),
                )

    def list_investors(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT pan, name, created_at FROM investors ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_investor(self, pan: str, name: str) -> dict:
        pan = (pan or "").strip().upper()
        name = (name or "").strip()
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
            raise ValueError("Enter a valid 10-character Indian PAN")
        if not name:
            raise ValueError("Investor name is required")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            is_first = connection.execute(
                "SELECT 1 FROM investors LIMIT 1"
            ).fetchone() is None
            connection.execute(
                "INSERT INTO investors (pan, name, created_at) VALUES (?, ?, ?)",
                (pan, name, datetime.now().isoformat(timespec="seconds")),
            )
            if is_first:
                legacy_collections = connection.execute(
                    "SELECT DISTINCT collection FROM portfolio_records "
                    "WHERE instr(collection, '::') = 0"
                ).fetchall()
                for row in legacy_collections:
                    collection = row["collection"]
                    connection.execute(
                        "UPDATE portfolio_records SET collection = ? WHERE collection = ?",
                        (f"{pan}::{collection}", collection),
                    )
                connection.execute(
                    "UPDATE upload_batches SET investor_pan = ? WHERE investor_pan = ''",
                    (pan,),
                )
                connection.execute(
                    "INSERT INTO app_settings (key, value) VALUES ('active_investor_pan', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (pan,),
                )
        return {"pan": pan, "name": name}

    def set_active_investor(self, pan: str) -> None:
        pan = (pan or "").strip().upper()
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM investors WHERE pan = ?", (pan,)
            ).fetchone() is None:
                raise ValueError("Investor not found")
            connection.execute(
                "INSERT INTO app_settings (key, value) VALUES ('active_investor_pan', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (pan,),
            )

    def get_active_investor(self) -> dict | None:
        pan = None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'active_investor_pan'"
            ).fetchone()
            if row:
                pan = row["value"]
            if not pan:
                row = connection.execute(
                    "SELECT pan FROM investors ORDER BY created_at LIMIT 1"
                ).fetchone()
                pan = row["pan"] if row else None
            if not pan:
                return None
            investor = connection.execute(
                "SELECT pan, name, created_at FROM investors WHERE pan = ?", (pan,)
            ).fetchone()
        return dict(investor) if investor else None
