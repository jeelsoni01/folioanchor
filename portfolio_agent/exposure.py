"""Deterministic stock-sector exposure from the supplied holding weights."""

import re
from decimal import Decimal

from .database import Database, DataError


def words(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def resolve_portfolio(name: str, names: tuple[str, ...]) -> str:
    query = words(name)
    if not query:
        raise DataError("Specify a portfolio name.")
    exact = [value for value in names if words(value) == query]
    if exact:
        return exact[0]
    matches = [value for value in names if set(query) <= set(words(value))]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise DataError("Ambiguous portfolio name: " + ", ".join(matches))
    raise DataError(f"No portfolio matches '{name}'.")


def name_in_question(question: str, names: tuple[str, ...]) -> str | None:
    text = " " + " ".join(words(question)) + " "
    matches = []
    for name in names:
        tokens = words(name)
        variants = [tokens]
        if tokens[-1:] in (("fund",), ("portfolio",)) and len(tokens) > 2:
            variants.append(tokens[:-1])
        if any(" " + " ".join(item) + " " in text for item in variants):
            matches.append(name)
    if not matches:
        return None
    longest = max(len(words(name)) for name in matches)
    best = [name for name in matches if len(words(name)) == longest]
    return best[0] if len(best) == 1 else None


def calculate_exposure(db: Database, portfolio_name: str, basis: str = "portfolio") -> dict:
    if basis not in ("portfolio", "equity"):
        raise DataError("Exposure basis must be 'portfolio' or 'equity'.")
    name = resolve_portfolio(portfolio_name, db.portfolios)
    holdings = db.query("""SELECT s.symbol, s.asset_type, sec.sector_name, h.current_weight
        FROM holdings h JOIN portfolios p USING (portfolio_id)
        JOIN securities s USING (security_id)
        LEFT JOIN sectors sec USING (sector_id)
        WHERE p.portfolio_name = :name""", {"name": name})
    totals: dict[str, Decimal] = {}
    equity = bonds = total = Decimal(0)
    contributions = []
    for symbol, asset, sector, raw_weight in holdings.rows:
        weight = Decimal(str(raw_weight))
        total += weight
        if asset == "Bond":
            bonds += weight
        else:
            equity += weight
            label = sector or "Unclassified"
            totals[label] = totals.get(label, Decimal(0)) + weight
            contributions.append({"symbol": symbol, "sector": label, "portfolio_weight_pct": float(weight * 100)})
    divisor = equity if basis == "equity" else Decimal(1)
    rows = [[sector, round(float(weight / divisor * 100), 6)]
            for sector, weight in totals.items()] if divisor else []
    rows.sort(key=lambda row: (-row[1], row[0]))
    warnings = []
    if total != Decimal(1):
        warnings.append(f"Supplied weights total {total * 100:g}%; the gap is not assumed to be cash.")
    if bonds:
        warnings.append(f"Bonds ({bonds * 100:g}% of portfolio weight) are excluded.")
    if not equity:
        warnings.append("This portfolio has no stock holdings to classify by sector.")
    return {
        "portfolio_name": name,
        "basis": basis,
        "columns": ["sector", "exposure_pct"],
        "rows": rows,
        "equity_weight_pct": float(equity * 100),
        "bond_weight_pct": float(bonds * 100),
        "total_weight_pct": float(total * 100),
        "warnings": warnings,
        "contributions": sorted(contributions, key=lambda row: (row["sector"], -row["portfolio_weight_pct"])),
        "formula": "100 × stock sector weight" + (" / total stock weight" if basis == "equity" else ""),
    }
