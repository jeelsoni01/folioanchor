"""Conservative local plans for common snapshot questions.

Each pattern consumes the whole normalized question. Anything with additional
filters or an unclear metric is left to the model planner.
"""

import re

from .exposure import name_in_question
from .planner import Plan


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _plan(sql: str, **parameters) -> Plan:
    return Plan(tool="sql", sql=sql, parameters=[{"name": key, "value": value}
                                             for key, value in parameters.items()])


def plan_common_question(question: str, db) -> Plan | None:
    q = " ".join(re.findall(r"[a-z0-9]+", question.casefold()))
    name = name_in_question(question, db.portfolios)

    if name:
        canonical_text = " ".join(re.findall(r"[a-z0-9]+", name.casefold()))
        short_text = re.sub(r" (?:fund|portfolio)$", "", canonical_text)
        names = f"(?:{re.escape(canonical_text)}|{re.escape(short_text)})"
        basis = "equity" if re.search(r"\bequity (?:normalized|only)\b", q) else "portfolio"
        exposure_forms = (
            rf"(?:what is|show|calculate) (?:the )?(?:equity normalized |equity only |stock )?sector (?:exposure|allocation|allocations|breakdown) (?:for|of) (?:the )?{names}",
            rf"(?:break down|show the breakdown of) (?:the )?{names} by stock sector(?: using (?:its |the )?supplied portfolio weights)?",
            rf"how is (?:the )?{names} distributed across sectors",
        )
        if any(re.fullmatch(form, q) for form in exposure_forms):
            return Plan(tool="exposure", portfolio_name=name, basis=basis)

    status_count = re.fullmatch(
        r"(?:how many|count|number of) (?:portfolios|funds) (?:are |are marked |have status )(active|passive)", q
    )
    if status_count:
        return _plan("SELECT COUNT(*) AS portfolio_count FROM portfolios WHERE lower(status)=:status",
                     status=status_count.group(1))

    asset_count = re.fullmatch(
        r"(?:how many|count|number of) (?:securities(?: in (?:this|the) snapshot)? (?:are |classified as )?|)(stocks?|bonds?)", q
    )
    if asset_count:
        asset = "Bond" if asset_count.group(1).startswith("bond") else "Stock"
        return _plan("SELECT COUNT(*) AS security_count FROM securities WHERE asset_type=:asset_type",
                     asset_type=asset)

    passive_names = re.fullmatch(
        r"(?:list|show) (active|passive) portfolio names and (?:their )?aum (?:largest first|from highest (?:aum )?to lowest)", q
    )
    if passive_names:
        return _plan("SELECT portfolio_name,total_aum FROM portfolios WHERE lower(status)=:status ORDER BY total_aum DESC",
                     status=passive_names.group(1))

    threshold = re.fullmatch(
        r"(?:list|show) (?:the )?(?:names of )?portfolios? (?:names )?(?:with|whose recorded) aum "
        r"(?:above|over|exceeds|exceeding|greater than) (\d+(?:\.\d+)?|one) "
        r"(million|billion)(?: from highest aum to lowest| highest aum to lowest)?", q
    )
    if threshold:
        number = 1 if threshold.group(1) == "one" else float(threshold.group(1))
        amount = int(number * (1_000_000_000 if threshold.group(2) == "billion" else 1_000_000))
        return _plan("SELECT portfolio_name FROM portfolios WHERE total_aum>:minimum ORDER BY total_aum DESC",
                     minimum=amount)

    top_aum = re.fullmatch(
        r"(?:show|list) (?:the )?(\d+|one|two|three|four|five|six|seven|eight|nine|ten) "
        r"(?:portfolios|funds) with (?:the )?(?:largest|highest) (?:recorded )?aum", q
    )
    if top_aum:
        count = NUMBER_WORDS.get(top_aum.group(1), None)
        count = count if count is not None else int(top_aum.group(1))
        if 1 <= count <= 100:
            return _plan("SELECT portfolio_name,total_aum FROM portfolios ORDER BY total_aum DESC LIMIT :n", n=count)

    if re.fullmatch(r"(?:which|what) portfolios have no performance records(?: list their names)?", q):
        return _plan("SELECT p.portfolio_name FROM portfolios p LEFT JOIN portfolio_performance pp "
                     "ON p.portfolio_id=pp.portfolio_id WHERE pp.portfolio_id IS NULL ORDER BY p.portfolio_name")

    if re.fullmatch(r"what is the latest performance date for each portfolio with performance data", q):
        return _plan("SELECT p.portfolio_name,MAX(pp.performance_date) AS latest_date "
                     "FROM portfolios p JOIN portfolio_performance pp USING(portfolio_id) "
                     "GROUP BY p.portfolio_id ORDER BY p.portfolio_name")

    combined = re.fullmatch(
        r"which portfolios hold both ([a-z0-9]+) and ([a-z0-9]+) and what is their "
        r"combined recorded weight as a percentage highest first", q
    )
    if combined:
        symbols = {symbol.casefold(): symbol for (symbol,) in db.query("SELECT symbol FROM securities").rows}
        first, second = (symbols.get(value) for value in combined.groups())
        if first and second and first != second:
            return _plan("SELECT p.portfolio_name,ROUND(SUM(h.current_weight)*100,2) AS combined_pct "
                         "FROM portfolios p JOIN holdings h USING(portfolio_id) "
                         "JOIN securities s USING(security_id) WHERE s.symbol IN (:first,:second) "
                         "GROUP BY p.portfolio_id HAVING COUNT(DISTINCT s.symbol)=2 "
                         "ORDER BY combined_pct DESC", first=first, second=second)
    return None
