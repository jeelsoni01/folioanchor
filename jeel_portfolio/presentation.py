"""Factual, human-readable summaries over already calculated results."""


LABELS = {
    "portfolio_name": "Portfolio", "exposure_pct": "Exposure (%)",
    "sector": "Sector", "sector_name": "Sector", "sector_percentage": "Sector share (%)",
    "total_aum": "Recorded AUM", "cost_basis": "Cost basis",
    "company_name": "Company", "symbol": "Symbol", "holding_id": "Holding ID",
    "latest_date": "Latest date", "avg_price": "Average price",
}


def display_value(value) -> str:
    if value is None:
        return "No data"
    if isinstance(value, float):
        return f"{value:,.6f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def present_answer(result: dict) -> tuple[str, str]:
    """Return an answer line and a short interpretation, without new calculations."""
    tool = result.get("tool")
    rows = result.get("rows") or []
    columns = result.get("columns") or []
    evidence = result.get("evidence") or {}

    if tool == "hybrid":
        compared = len(evidence.get("comparison_rows", rows))
        basis = "equity allocation" if evidence.get("basis") == "equity" else "whole portfolio"
        return result["message"], f"Compared {compared} recorded portfolios. Percentages use supplied stock weights as a share of the {basis}; bonds are excluded."

    if tool == "exposure_calculator":
        fund = evidence.get("portfolio", "This portfolio")
        basis = "equity allocation" if evidence.get("basis") == "equity" else "whole portfolio"
        if rows:
            sector, percent = rows[0]
            lead = f"{fund}: {sector} is the largest stock sector at {display_value(percent)}%."
        else:
            lead = f"{fund} has no stock-sector exposure in the supplied holdings."
        return lead, f"Percentages use supplied holding weights as a share of the {basis}; bonds are excluded."

    if not rows:
        return "No matching records were found.", "The supplied snapshot contains no rows for this question."

    if len(rows) == len(columns) == 1:
        label = LABELS.get(columns[0], columns[0].replace("_", " ").capitalize())
        return f"{label}: {display_value(rows[0][0])}", "Calculated from the supplied portfolio snapshot."

    if "cost_basis" in columns and "symbol" in columns and rows:
        symbol = rows[0][columns.index("symbol")]
        cost = rows[0][columns.index("cost_basis")]
        return f"Top holding by cost basis: {symbol} ({display_value(cost)}).", f"Showing {len(rows)} matching holdings in the table."

    if "portfolio_name" in columns:
        if len(rows) == 1:
            return f"Matching portfolio: {rows[0][columns.index('portfolio_name')]}", "See its recorded values in the table."
        return f"{len(rows)} portfolios match this question.", "The table shows each recorded result."

    return f"{len(rows)} matching records found.", "The table shows the recorded values used to answer."
