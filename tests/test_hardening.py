"""Independent accounting and failure-boundary checks for the supplied snapshot."""

import csv
import shutil
from decimal import Decimal

import pytest
from pydantic import ValidationError

from jeel_portfolio.cache import AnswerCache
from jeel_portfolio.database import DataError, Database, ROOT
from jeel_portfolio.exposure import calculate_exposure, resolve_portfolio
from jeel_portfolio.planner import Plan


def read_csv(name):
    with (ROOT / "data" / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


PORTFOLIO_NAMES = tuple(row["portfolio_name"] for row in read_csv("portfolios"))


@pytest.fixture
def db():
    value = Database()
    try:
        yield value
    finally:
        value.close()


@pytest.mark.parametrize("sql", [
    "DELETE FROM portfolios",
    "UPDATE portfolios SET status='Passive'",
    "INSERT INTO portfolios(portfolio_id, portfolio_name) VALUES (99, 'bad')",
    "CREATE TABLE hidden(x)",
    "DROP TABLE holdings",
    "ALTER TABLE portfolios ADD COLUMN hidden TEXT",
    "ATTACH DATABASE 'other.db' AS other",
    "DETACH DATABASE main",
    "PRAGMA table_info(portfolios)",
    "VACUUM",
    "EXPLAIN SELECT * FROM portfolios",
    "SELECT name FROM sqlite_master",
    "SELECT name FROM sqlite_schema",
    "SELECT load_extension('unsafe') FROM portfolios",
    "SELECT randomblob(8) FROM portfolios",
    "SELECT 42",
    "WITH constant AS (SELECT 42) SELECT * FROM constant",
    "SELECT portfolio_name FROM portfolios; SELECT * FROM holdings",
])
def test_sql_rejects_distinct_unsafe_or_ungrounded_queries(db, sql):
    with pytest.raises(DataError):
        db.query(sql)


@pytest.mark.parametrize(("sql", "expected"), [
    ("SELECT COUNT(*) FROM portfolios", 13),
    ("SELECT COUNT(*) FROM holdings", 95),
    ("SELECT COUNT(*) FROM portfolios WHERE status='Active'", 10),
    ("SELECT COUNT(*) FROM portfolios WHERE status='Passive'", 3),
    ("SELECT SUM(total_aum) FROM portfolios WHERE lower(target_risk_level)='high'", 85_000_000),
])
def test_sql_allows_grounded_financial_queries(db, sql, expected):
    assert db.query(sql).rows == ((expected,),)


@pytest.mark.parametrize("limit", [0, -1, 501, 10_000])
def test_sql_rejects_out_of_range_result_limits(db, limit):
    with pytest.raises(DataError, match="Result limit"):
        db.query("SELECT holding_id FROM holdings", limit=limit)


@pytest.mark.parametrize("limit", [1, 2])
def test_sql_reports_truncation_without_exceeding_limit(db, limit):
    result = db.query("SELECT holding_id FROM holdings ORDER BY holding_id", limit=limit)
    assert result.truncated
    assert result.rows == tuple((number,) for number in range(1, limit + 1))


@pytest.mark.parametrize(("question", "expected"), [
    ("growth equity", "Growth Equity Fund"),
    ("TECH INNOVATION FUND", "Tech Innovation Fund"),
    ("esg sustainable", "ESG Sustainable Fund"),
    ("fixed income plus", "Fixed Income Plus"),
    ("Total Stock Market Index Fund", "Total Stock Market Index Fund"),
])
def test_unique_portfolio_name_resolution(db, question, expected):
    assert resolve_portfolio(question, db.portfolios) == expected


@pytest.mark.parametrize(("question", "message"), [
    ("international", "Ambiguous"),
    ("", "Specify"),
    ("imaginary retirement fund", "No portfolio matches"),
])
def test_portfolio_name_refuses_ambiguous_or_missing_names(db, question, message):
    with pytest.raises(DataError, match=message):
        resolve_portfolio(question, db.portfolios)


def expected_exposure(portfolio_name, basis):
    """Separate CSV oracle, independent of the app's SQLite and calculator."""
    portfolios = {row["portfolio_name"]: row["portfolio_id"] for row in read_csv("portfolios")}
    securities = {row["security_id"]: row for row in read_csv("securities")}
    sectors = {row["sector_id"]: row["sector_name"] for row in read_csv("sectors")}
    groups = {}
    equity = bonds = Decimal(0)
    for holding in read_csv("holdings"):
        if holding["portfolio_id"] != portfolios[portfolio_name]:
            continue
        weight = Decimal(holding["current_weight"])
        security = securities[holding["security_id"]]
        if security["asset_type"] == "Bond":
            bonds += weight
        else:
            equity += weight
            sector = sectors.get(security["sector_id"], "Unclassified")
            groups[sector] = groups.get(sector, Decimal(0)) + weight
    divisor = equity if basis == "equity" and equity else Decimal(1)
    return {sector: float(weight / divisor * 100) for sector, weight in groups.items()}, float(equity * 100), float(bonds * 100)


@pytest.mark.parametrize("portfolio_name", PORTFOLIO_NAMES)
@pytest.mark.parametrize("basis", ["portfolio", "equity"])
def test_every_portfolio_exposure_matches_independent_csv_oracle(db, portfolio_name, basis):
    result = calculate_exposure(db, portfolio_name, basis)
    expected, equity_pct, bond_pct = expected_exposure(portfolio_name, basis)
    actual = dict(result["rows"])
    assert set(actual) == set(expected)
    for sector, percentage in expected.items():
        assert actual[sector] == pytest.approx(percentage, abs=1e-5)
    assert result["equity_weight_pct"] == pytest.approx(equity_pct)
    assert result["bond_weight_pct"] == pytest.approx(bond_pct)
    assert sum(actual.values()) == pytest.approx(100 if basis == "equity" and equity_pct else equity_pct, abs=1e-4)


@pytest.mark.parametrize("plan_data", [
    {"tool": "sql"},
    {"tool": "hybrid", "sector": "Technology"},
    {"tool": "hybrid", "sql": "SELECT portfolio_name FROM portfolios"},
    {"tool": "exposure"},
    {"tool": "exposure", "portfolio_name": "Balanced Portfolio", "basis": "unknown"},
    {"tool": "sql", "sql": "SELECT COUNT(*) FROM portfolios", "parameters": [{"name": "x", "value": 1}, {"name": "x", "value": 2}]},
    {"tool": "sql", "sql": "SELECT COUNT(*) FROM portfolios", "top_n": -1},
    {"tool": "sql", "sql": "SELECT COUNT(*) FROM portfolios", "top_n": 101},
    {"tool": "delete", "sql": "DELETE FROM portfolios"},
])
def test_invalid_model_plan_is_rejected_before_a_tool_runs(plan_data):
    with pytest.raises(ValidationError):
        Plan.model_validate(plan_data)


@pytest.mark.parametrize(("question", "same_key"), [
    ("What is AUM?", "  what   IS aum? "),
    ("Technology exposure", "TECHNOLOGY EXPOSURE"),
    ("Count portfolios", "count portfolios"),
])
def test_cache_normalizes_case_and_whitespace(tmp_path, question, same_key):
    cache = AnswerCache(tmp_path / "answers.sqlite3", "data-v1", "model-v1")
    try:
        cache.put(question, {"status": "ok", "rows": [[13]]})
        assert cache.get(same_key) == ({"status": "ok", "rows": [[13]]}, "memory")
    finally:
        cache.close()


@pytest.mark.parametrize(("change", "message"), [
    ("header", "Columns"),
    ("negative_weight", "Holding weights"),
    ("nan_weight", "Holding weights"),
    ("broken_foreign_key", "Could not load holdings.csv"),
    ("short_row", "Could not load holdings.csv"),
    ("empty_file", "holdings.csv is empty"),
])
def test_corrupt_snapshot_fails_loading(tmp_path, change, message):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copy2(ROOT / "database_schema.sql", tmp_path / "database_schema.sql")
    path = tmp_path / "data" / "holdings.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    if change == "empty_file":
        path.write_text("", encoding="utf-8")
    elif change == "header":
        lines[0] = lines[0].replace("current_weight", "wrong_weight")
    else:
        cells = lines[1].split(",")
        if change == "short_row":
            cells.pop()
        elif change == "broken_foreign_key":
            cells[2] = "999999"
        else:
            cells[6] = "-0.1" if change == "negative_weight" else "NaN"
        lines[1] = ",".join(cells)
    if change != "empty_file":
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(DataError, match=message):
        value = Database(tmp_path)
        value.close()
