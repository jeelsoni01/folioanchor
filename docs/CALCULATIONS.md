# Calculation guide

This project loads the nine supplied CSV tables into an in-memory SQLite database. It does not fetch prices or holdings from a live service. Every answer should be interpreted as a calculation over that fixed snapshot.

## Recorded AUM

`portfolios.total_aum` is the supplied Assets Under Management field. A question about AUM reads or aggregates that field after applying the requested portfolio filters. It does **not** reconstruct AUM from `holdings.quantity × securities.current_price`. The files do not state a currency, so the interface displays the number without a currency symbol.

## Stock-sector exposure

For a named portfolio, join its holdings to securities and sectors. Add `holdings.current_weight` for **stock** positions in each sector; ignore bond positions in the numerator.

| Basis | Calculation |
| --- | --- |
| Whole portfolio (default) | `100 × stock weight in sector` |
| Equity-only, when explicitly requested | `100 × stock weight in sector ÷ total stock weight` |

The two bases answer different questions. For example, a portfolio with 22% Technology stock weight and 64% bonds has **22% Technology exposure on the whole-portfolio basis**; the equity-only percentage is higher because bonds leave the denominator. If the supplied weights do not total 100%, the tool reports that gap and does not assume it is cash.

## Value and price questions

When a question explicitly asks for holding market value, the snapshot calculation is `quantity × current_price`. It is a different metric from recorded AUM and from weight-based exposure. The supplied files do not include timestamps for each holding and current price, so the result is not represented as a live valuation.

## Inspecting an answer

The CLI prints the calculation route; `--json` includes rows, warnings, and evidence. The Streamlit desk places the answer first and offers an evidence expander with the query and parameters or the exposure contributions. The evaluator compares answers with independent reference SQL or CSV calculations and preserves the order of ranked results.
