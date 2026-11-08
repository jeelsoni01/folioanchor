from evaluate import same_rows, reference_exposure, project_requested_columns
from jeel_portfolio.database import ROOT


def test_reference_exposure_is_independent_and_excludes_bonds():
    rows = reference_exposure(ROOT, "Balanced Portfolio")
    assert ["Technology", 22.0] in rows
    assert sum(row[1] for row in rows) == 36.0


def test_evaluator_detects_wrong_values_and_ranking():
    assert same_rows([[1.000001], [2]], [[2], [1]])
    assert not same_rows([[1], [3]], [[1], [2]])
    assert not same_rows([[2], [1]], [[1], [2]], ordered=True)


def test_evaluator_accepts_named_extra_fields_but_not_missing_fields():
    rows = [["AAPL", "Apple", "Stock"]]
    assert project_requested_columns(["symbol", "company_name", "asset_type"], rows, ["symbol", "company_name"]) == [["AAPL", "Apple"]]
    assert project_requested_columns(["symbol", "cost_basis"], [["AAPL", 100]], ["holding_id", "symbol", "quantity", "cost_basis"]) is None


def test_provider_interruption_preserves_previous_complete_report(tmp_path, monkeypatch):
    import evaluate
    from jeel_portfolio.database import Database
    class UnavailableAgent:
        def __init__(self, cache=False):
            self.db = Database()
        def answer(self, question, force_gemini=False):
            return {"status":"error","error_code":"provider_unavailable","message":"Network unavailable","elapsed_ms":1.0}
        def close(self):
            self.db.close()
    monkeypatch.setattr(evaluate, "PortfolioAgent", UnavailableAgent)
    output = tmp_path / "gemini-evaluation.json"
    output.write_text('{"passed":7,"status":"complete"}', encoding="utf-8")
    report = evaluate.run(ids={1}, output=output, gemini_only=True)
    assert report["status"] == "interrupted"
    assert report["accuracy_pct"] is None
    assert output.read_text(encoding="utf-8") == '{"passed":7,"status":"complete"}'
    assert (tmp_path / "gemini-evaluation-interrupted.json").exists()
