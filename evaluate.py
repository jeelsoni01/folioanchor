"""Compare every supplied case with independently executed reference results."""

import argparse
import csv
import json
import math
import statistics
import time
from collections import defaultdict
from pathlib import Path

from jeel_portfolio.agent import PortfolioAgent
from jeel_portfolio.database import ROOT


def reference_exposure(root: Path, name: str, basis: str = "portfolio"):
    def read(table):
        with (root / "data" / f"{table}.csv").open(encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))
    portfolios = {r["portfolio_id"]:r["portfolio_name"] for r in read("portfolios")}
    securities = {r["security_id"]:r for r in read("securities")}
    sectors = {r["sector_id"]:r["sector_name"] for r in read("sectors")}
    result = defaultdict(float)
    for holding in read("holdings"):
        if portfolios[holding["portfolio_id"]] != name:
            continue
        security = securities[holding["security_id"]]
        if security["asset_type"] == "Stock":
            result[sectors.get(security["sector_id"], "Unclassified")] += float(holding["current_weight"]) * 100
    denominator = sum(result.values()) / 100 if basis == "equity" else 1
    return [[sector, round(weight / denominator, 6)] for sector, weight in result.items()] if denominator else []


def same_rows(actual, expected, ordered=False):
    if len(actual) != len(expected):
        return False
    if not ordered:
        actual = sorted(actual, key=lambda row: str(row).casefold())
        expected = sorted(expected, key=lambda row: str(row).casefold())
    for left, right in zip(actual, expected):
        if len(left) != len(right):
            return False
        for a, b in zip(left, right):
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if not math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-4):
                    return False
            elif str(a).casefold().strip() != str(b).casefold().strip():
                return False
    return True


def project_requested_columns(actual_columns, actual_rows, expected_columns):
    """Allow extra evidence fields only when all requested fields are named uniquely."""
    actual = [name.casefold() for name in actual_columns]
    expected = [name.casefold() for name in expected_columns]
    if all(actual.count(name) == 1 for name in expected):
        positions = [actual.index(name) for name in expected]
        return [[row[i] for i in positions] for row in actual_rows]
    return actual_rows if len(actual) == len(expected) else None


def run(ids=None, output=None, delay=0, gemini_only=False, cases_path=None):
    cases_path = Path(cases_path) if cases_path else ROOT / "ground_truth_dataset.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["questions"]
    output = Path(output) if output else None
    interrupted_path = output.with_name(output.stem + "-interrupted" + output.suffix) if output else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
    agent = PortfolioAgent(cache=False)
    records = []
    try:
        for case in cases:
            if ids and case["id"] not in ids:
                continue
            result = agent.answer(case["question"], force_gemini=gemini_only)
            truth = case["ground_truth"]
            if case["type"] == "text2sql":
                expected = agent.db.query(truth["sql_query"])
                compared = project_requested_columns(result.get("columns", []), result.get("rows", []), expected.columns)
                passed = result["status"] == "ok" and result["tool"] == "sql_query" and compared is not None and same_rows(compared, expected.rows, ordered=case.get("ordered", case["id"] == 5))
                if passed and case.get("ranked_by") == "last_desc":
                    passed = all(float(left[-1]) >= float(right[-1]) for left, right in zip(compared, compared[1:]))
                expected_rows = [list(r) for r in expected.rows]
            else:
                expected_rows = reference_exposure(ROOT, truth["parameters"]["portfolio_name"], truth["parameters"].get("basis", "portfolio"))
                passed = result["status"] == "ok" and result["tool"] == "exposure_calculator" and same_rows(result["rows"], expected_rows)
            unavailable = result.get("error_code") == "provider_unavailable"
            record = {"id":case["id"],"question":case["question"],"pass":None if unavailable else passed,"route":result.get("route"),"latency_ms":result["elapsed_ms"],"actual_columns":result.get("columns"),"actual_rows":result.get("rows"),"expected_rows":expected_rows,"evidence":result.get("evidence"),"error":result.get("message") if result["status"] != "ok" else None}
            records.append(record)
            if interrupted_path:
                interrupted_path.write_text(json.dumps({"status":"in_progress","mode":"gemini_only" if gemini_only else "hybrid","cases":records}, indent=2), encoding="utf-8")
            label = "UNAVAILABLE" if unavailable else ("PASS" if passed else "FAIL")
            print(f"{label} {case['id']}: {case['question']} [{result.get('route')}; {result['elapsed_ms']:.3f} ms]", flush=True)
            if not passed and result["status"] != "ok":
                print("  Reason:", result["message"], flush=True)
            if gemini_only and result.get("error_code") == "provider_unavailable":
                print("Stopping live evaluation after provider failure; no accuracy score is inferred for unrun cases.", flush=True)
                break
            if delay:
                time.sleep(delay)
    finally:
        agent.close()
    latencies = [r["latency_ms"] for r in records]
    passed_count = sum(r["pass"] is True for r in records)
    failed_count = sum(r["pass"] is False for r in records)
    unavailable_count = sum(r["pass"] is None for r in records)
    planned_total = len([case for case in cases if not ids or case["id"] in ids])
    completed = unavailable_count == 0 and len(records) == planned_total
    report = {"status":"complete" if completed else "interrupted","passed":passed_count,"failed":failed_count,"unavailable":unavailable_count,"attempted":len(records),"planned_total":planned_total,"accuracy_pct":round(100*passed_count/planned_total,2) if planned_total and completed else None,"median_latency_ms":round(statistics.median(latencies),3) if latencies else None,"mode":"gemini_only" if gemini_only else "hybrid","note":"Supplied cases are development cases, not unseen holdout questions. A provider failure stops the live run and is not counted as a model accuracy miss.","cases":records}
    if output:
        destination = output if completed else interrupted_path
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if completed:
            interrupted_path.unlink(missing_ok=True)
        print("Report:", destination)
    print(f"Result: {passed_count} passed, {failed_count} failed, {unavailable_count} unavailable, {planned_total} planned; median {report['median_latency_ms']} ms.")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--delay", type=float, default=0)
    parser.add_argument("--gemini-only", action="store_true", help="Bypass local grammar to test model planning on every case")
    parser.add_argument("--cases", type=Path, help="Alternative question set in the supplied ground-truth format")
    args = parser.parse_args()
    ids = set(args.ids) if args.ids else None
    if args.output:
        destination = args.output
    else:
        label = "gemini-evaluation" if args.gemini_only else "evaluation"
        if ids:
            label += "-ids-" + "-".join(str(item) for item in sorted(ids))
        destination = Path("reports") / f"{label}.json"
    report = run(ids, destination, args.delay, args.gemini_only, args.cases)
    raise SystemExit(0 if report["passed"] == report["planned_total"] else (2 if report["unavailable"] else 1))
