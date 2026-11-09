"""Load the supplied snapshot and expose bounded, read-only SQLite queries."""

import csv
import hashlib
import math
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "sectors", "securities", "benchmarks", "portfolios", "holdings",
    "transactions", "historical_prices", "portfolio_performance", "risk_metrics",
)
FUNCTIONS = {
    "count", "sum", "total", "avg", "min", "max", "round", "abs",
    "coalesce", "ifnull", "nullif", "lower", "upper", "trim", "like",
    "date", "datetime", "strftime", "julianday", "length", "substr",
    "row_number", "rank", "dense_rank", "lag", "lead",
}


class DataError(Exception):
    pass


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple, ...]
    truncated: bool = False


class Database:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.execute("PRAGMA foreign_keys=ON")
        schema_file = self.root / "database_schema.sql"
        self.schema = schema_file.read_text(encoding="utf-8")
        self.connection.executescript(self.schema)
        digest = hashlib.sha256(schema_file.read_bytes())
        self.counts = {}
        for table in TABLES:
            path = self.root / "data" / f"{table}.csv"
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
            with path.open(newline="", encoding="utf-8-sig") as file:
                reader = csv.reader(file)
                try:
                    header = next(reader)
                except StopIteration as exc:
                    raise DataError(f"{path.name} is empty.") from exc
                expected = [row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")]
                if header != expected:
                    raise DataError(f"Columns in {path.name} do not match the schema.")
                rows = [[None if cell == "" else cell for cell in row] for row in reader]
            try:
                self.connection.executemany(
                    f"INSERT INTO {table} VALUES ({','.join('?' for _ in header)})", rows
                )
            except sqlite3.Error as exc:
                raise DataError(f"Could not load {path.name}: {exc}") from exc
            self.counts[table] = len(rows)
        self.connection.commit()
        if self.connection.execute("PRAGMA foreign_key_check").fetchall():
            raise DataError("The supplied data has broken foreign keys.")
        if any(not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0 for (weight,) in
               self.connection.execute("SELECT current_weight FROM holdings")):
            raise DataError("Holding weights must be finite and nonnegative.")
        self.fingerprint = digest.hexdigest()
        self.portfolios = tuple(row[0] for row in self.connection.execute(
            "SELECT portfolio_name FROM portfolios"))
        self.sectors = tuple(row[0] for row in self.connection.execute(
            "SELECT sector_name FROM sectors"))
        self.schema_summary = "\n".join(
            f"{table}({', '.join(row[1] for row in self.connection.execute(f'PRAGMA table_info({table})'))})"
            for table in TABLES
        )
        self.connection.execute("PRAGMA query_only=ON")
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20_000)
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
        self.connection.set_authorizer(self._authorize)

    @staticmethod
    def _authorize(action, table, function, database, source):
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and table in TABLES:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (function or "").lower() in FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def query(self, sql: str, parameters: dict | None = None, limit: int = 500) -> QueryResult:
        if not re.match(r"\s*(SELECT|WITH)\b", sql, re.IGNORECASE) or len(sql) > 20_000:
            raise DataError("Only a single read-only SELECT query is allowed.")
        if not 1 <= limit <= 500:
            raise DataError("Result limit must be between 1 and 500.")
        with self.lock:
            deadline = time.monotonic() + 2
            steps = 0
            reads_snapshot = False

            def authorize(action, table, function, database, source):
                nonlocal reads_snapshot
                decision = self._authorize(action, table, function, database, source)
                if decision == sqlite3.SQLITE_OK and action == sqlite3.SQLITE_READ and table in TABLES:
                    reads_snapshot = True
                return decision

            def progress():
                nonlocal steps
                steps += 1
                return int(steps > 2000 or time.monotonic() > deadline)

            self.connection.set_progress_handler(progress, 1000)
            self.connection.set_authorizer(authorize)
            try:
                cursor = self.connection.execute(sql, parameters or {})
                if not reads_snapshot:
                    raise DataError("The query must read at least one supplied table.")
                rows = cursor.fetchmany(limit + 1)
                return QueryResult(tuple(col[0] for col in cursor.description),
                                   tuple(tuple(row) for row in rows[:limit]), len(rows) > limit)
            except sqlite3.Error as exc:
                raise DataError(f"Query failed: {exc}") from exc
            finally:
                self.connection.set_progress_handler(None, 0)
                self.connection.set_authorizer(self._authorize)

    def close(self):
        with self.lock:
            self.connection.close()
