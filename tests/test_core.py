from pathlib import Path

import pytest

from jeel_portfolio.agent import PortfolioAgent
from jeel_portfolio.cache import AnswerCache
from jeel_portfolio.database import DataError, Database, ROOT
from jeel_portfolio.exposure import calculate_exposure, resolve_portfolio


@pytest.fixture
def db():
    value = Database()
    yield value
    value.close()


def test_sql_guard_blocks_writes_and_privileged_functions(db):
    for sql in ("DELETE FROM portfolios", "SELECT load_extension('x')", "PRAGMA table_info(portfolios)", "SELECT name FROM sqlite_master", "SELECT 42"):
        with pytest.raises(DataError):
            db.query(sql)
    assert db.query("SELECT COUNT(*) FROM portfolios").rows == ((13,),)


def test_sql_parameters_and_result_budget(db):
    result = db.query("SELECT portfolio_name FROM portfolios WHERE status=:status", {"status":"Active' OR 1=1 --"})
    assert result.rows == ()
    with pytest.raises(DataError):
        db.query("SELECT * FROM holdings", limit=0)
    with pytest.raises(DataError):
        db.query("SELECT * FROM holdings; DELETE FROM holdings")
    limited = db.query("SELECT holding_id FROM holdings", limit=2)
    assert len(limited.rows) == 2 and limited.truncated


def test_exposure_excludes_bonds_and_preserves_portfolio_basis(db):
    mixed = calculate_exposure(db, "Balanced Portfolio")
    assert ["Technology", 22.0] in mixed["rows"]
    assert mixed["bond_weight_pct"] == 64.0
    assert mixed["equity_weight_pct"] == 36.0
    equity = calculate_exposure(db, "Balanced Portfolio", "equity")
    assert ["Technology", pytest.approx(61.111111, abs=1e-5)] in equity["rows"]
    bonds = calculate_exposure(db, "Fixed Income Plus")
    assert bonds["rows"] == []


def test_ambiguous_name_is_not_guessed(db):
    with pytest.raises(DataError, match="Ambiguous"):
        resolve_portfolio("international", db.portfolios)


def test_incomplete_weight_is_reported_without_rescaling(db):
    exposure = calculate_exposure(db, "Total Stock Market Index Fund")
    assert exposure["total_weight_pct"] == 98.0
    assert sum(row[1] for row in exposure["rows"]) == pytest.approx(98.0)
    assert any("gap" in item for item in exposure["warnings"])


def test_cache_key_changes_with_dataset_and_model(tmp_path):
    path = tmp_path / "answers.sqlite3"
    one = AnswerCache(path, "dataset1", "model1")
    one.put("Question?", {"status":"ok","rows":[[1]]})
    assert one.get(" QUESTION? ")[1] == "memory"
    one.close()
    same = AnswerCache(path, "dataset1", "model1")
    assert same.get("question?")[1] == "disk"
    changed = AnswerCache(path, "dataset2", "model1")
    assert changed.get("question?") is None
    other_model = AnswerCache(path, "dataset1", "model2")
    assert other_model.get("question?") is None
    same.close()
    changed.close()
    other_model.close()


def test_agent_uses_gemini_for_unseen_question_without_eval_answer_lookup(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        from jeel_portfolio.planner import Plan
        called = []
        def fake(question, db, previous_error=""):
            called.append(question)
            return Plan(tool="sql", sql="SELECT portfolio_name FROM portfolios ORDER BY total_aum DESC LIMIT 1")
        monkeypatch.setattr(agent.planner, "plan", fake)
        result = agent.answer("Which fund has the most AUM?")
        assert result["status"] == "ok"
        assert result["route"] == "gemini_sql"
        assert called == ["Which fund has the most AUM?"]
    finally:
        agent.close()


def test_gemini_only_mode_bypasses_fast_path(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        from jeel_portfolio.planner import Plan
        seen = []
        def fake(question, db, previous_error=""):
            seen.append(question)
            return Plan(tool="sql", sql="SELECT COUNT(*) FROM portfolios")
        monkeypatch.setattr(agent.planner, "plan", fake)
        result = agent.answer("How many portfolios do we have in total?", force_gemini=True)
        assert result["route"] == "gemini_sql"
        assert seen
    finally:
        agent.close()


def test_gemini_sql_repair_is_bounded(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        from jeel_portfolio.planner import Plan
        plans = iter([Plan(tool="sql", sql="SELECT absent FROM portfolios"), Plan(tool="sql", sql="SELECT COUNT(*) FROM portfolios")])
        calls = []
        def fake(question, db, previous_error=""):
            calls.append(previous_error)
            return next(plans)
        monkeypatch.setattr(agent.planner, "plan", fake)
        result = agent.answer("Give me the portfolio census")
        assert result["status"] == "ok" and result["rows"] == [[13]]
        assert len(calls) == 2 and "Query failed" in calls[1]
    finally:
        agent.close()


def test_provider_failure_is_separate_from_wrong_answer(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        from jeel_portfolio.planner import ProviderUnavailable
        def fail(*_):
            raise ProviderUnavailable("Service temporarily unavailable")
        monkeypatch.setattr(agent.planner, "plan", fail)
        result = agent.answer("Which fund has the most AUM?")
        assert result["error_code"] == "provider_unavailable"
    finally:
        agent.close()


def test_hybrid_filters_portfolios_then_uses_exposure_calculator():
    agent = PortfolioAgent(cache=False)
    try:
        result = agent.answer("Which active high-risk portfolios have the highest Technology sector exposure?")
        assert result["status"] == "ok"
        assert result["tool"] == "hybrid"
        assert result["route"] == "fast_hybrid"
        assert result["rows"]
        assert all(0 <= row[1] <= 100 for row in result["rows"])
        assert len(result["rows"]) == 1
        assert result["rows"][0] == ["Tech Innovation Fund", 100.0]
        assert result["evidence"]["cohort_size"] == agent.db.query("SELECT COUNT(*) FROM portfolios WHERE status='Active' AND lower(target_risk_level)='high'").rows[0][0]
    finally:
        agent.close()


def test_hybrid_rejects_invalid_cohort_sql(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        from jeel_portfolio.planner import Plan
        monkeypatch.setattr(agent.planner, "plan", lambda *_: Plan(tool="hybrid", sql="SELECT portfolio_name,total_aum FROM portfolios", sector="Technology"))
        result = agent.answer("Compare Tech concentration")
        assert result["status"] == "error"
        assert "one complete portfolio_name" in result["message"]
    finally:
        agent.close()


def test_provider_wall_timeout_is_bounded(monkeypatch, db):
    import time
    from types import SimpleNamespace
    from jeel_portfolio.planner import GeminiPlanner, ProviderUnavailable
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    planner = GeminiPlanner("test-model")
    def slow(**_):
        time.sleep(0.2)
        return SimpleNamespace(text='{"tool":"clarify","clarification":"test"}')
    planner.client = SimpleNamespace(models=SimpleNamespace(generate_content=slow))
    planner.wall_seconds = 0.01
    from google.genai import types  # warm SDK import; measure only the request bound
    started = time.monotonic()
    with pytest.raises(ProviderUnavailable, match="did not respond"):
        planner.plan("A question", db)
    assert time.monotonic() - started < 0.1
    with pytest.raises(ProviderUnavailable, match="still finishing"):
        planner.plan("Another question", db)
    planner.pending[2].join(timeout=2)
    assert not planner.pending[2].is_alive()
    plan = planner.plan("A question", db)
    assert plan.tool == "clarify"


def test_invalid_model_plan_gets_one_correction(monkeypatch, db):
    from types import SimpleNamespace
    from jeel_portfolio.planner import GeminiPlanner
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    planner = GeminiPlanner("test-model")
    responses = iter(['{"not_a_plan":true}', '{"tool":"sql","sql":"SELECT COUNT(*) FROM portfolios"}'])
    calls = []
    def generate(**_):
        calls.append(1)
        return SimpleNamespace(text=next(responses))
    planner.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    result = planner.plan("Count funds", db)
    assert result.tool == "sql" and len(calls) == 2


def test_repeated_uncached_gemini_question_starts_a_new_request(monkeypatch, db):
    from types import SimpleNamespace
    from jeel_portfolio.planner import GeminiPlanner

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    planner = GeminiPlanner("test-model")
    calls = []

    def generate(**_):
        calls.append(1)
        return SimpleNamespace(text='{"tool":"sql","sql":"SELECT COUNT(*) FROM portfolios"}')

    planner.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    first = planner.plan("Count portfolios", db)
    second = planner.plan("Count portfolios", db)
    assert first.tool == second.tool == "sql"
    assert len(calls) == 2


def test_fast_router_does_not_drop_unhandled_filters():
    agent = PortfolioAgent(cache=False)
    try:
        for question in (
            "How many portfolios do we have in India?",
            "How many portfolios have no performance records?",
            "Which securities are outside the Technology sector?",
            "What is the average price of securities in the Technology sector?",
            "What is the Technology sector exposure for the Balanced Portfolio by market value?",
            "Which securities are in the Technology sector and cost less than 200?",
            "Show me the top 5 holdings by cost basis in the Growth Equity Fund purchased after 2020",
            "What are sector exposures for the Tech Innovation Fund as of 2020?",
            "For each portfolio, show the total value of Technology sector holdings and what percentage it represents of the total portfolio value, only active portfolios",
            "Find active portfolios that have holdings in more than 5 different sectors and show their diversification metrics",
            "What is the total AUM for high-risk portfolios created after 2020?",
            "What is the total AUM for high risk portfolios in India?",
            "What are the sector exposures for Tech Innovation Fund with more than five holdings?",
        ):
            assert agent._fast_plan(question) is None, question
        result = agent.answer("How many active high risk portfolios?")
        expected = agent.db.query("SELECT COUNT(*) FROM portfolios WHERE lower(status)='active' AND lower(target_risk_level)='high'").rows[0][0]
        assert result["rows"] == [[expected]]
    finally:
        agent.close()


def test_market_value_breakdown_rejects_zero_fill_and_repairs(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        question = "For each portfolio, show the total value of Technology sector holdings and what percentage it represents of the total portfolio value"
        from jeel_portfolio.planner import Plan
        valid = agent._fast_plan(question)
        wrong = Plan(tool="sql", sql="SELECT portfolio_name,0 AS sector_value,1 AS total_value,0 AS sector_percentage FROM portfolios")
        plans = iter([wrong, valid])
        feedback = []
        def fake(question, db, previous_error=""):
            feedback.append(previous_error)
            return next(plans)
        monkeypatch.setattr(agent.planner, "plan", fake)
        result = agent.answer(question, force_gemini=True)
        assert result["status"] == "ok" and len(result["rows"]) == 8
        assert len(feedback) == 2 and "portfolios holding" in feedback[1]
    finally:
        agent.close()


def test_transient_read_error_retries_once(monkeypatch, db):
    from types import SimpleNamespace
    import httpx
    from jeel_portfolio.planner import GeminiPlanner
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    planner = GeminiPlanner("test-model")
    calls = []
    def generate(**_):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadError("connection dropped")
        return SimpleNamespace(text='{"tool":"sql","sql":"SELECT COUNT(*) FROM portfolios"}')
    planner.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    result = planner.plan("Count portfolios", db)
    assert result.tool == "sql" and len(calls) == 2


def test_total_aum_plan_and_value_are_guarded(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        question = "What is the total Assets Under Management (AUM) for portfolios with high target risk level?"
        from jeel_portfolio.planner import Plan
        wrong = Plan(tool="sql", sql="SELECT total_aum FROM portfolios WHERE target_risk_level='High'")
        correct = agent._fast_plan(question)
        plans = iter([wrong, correct])
        feedback = []
        def fake(question, db, previous_error=""):
            feedback.append(previous_error)
            return next(plans)
        monkeypatch.setattr(agent.planner, "plan", fake)
        result = agent.answer(question, force_gemini=True)
        assert result["status"] == "ok"
        assert result["rows"] == [[agent.db.query("SELECT SUM(total_aum) FROM portfolios WHERE lower(target_risk_level)='high'").rows[0][0]]]
        assert len(feedback) == 2 and "SUM" in feedback[1]
    finally:
        agent.close()


def test_total_aum_with_creation_date_accepts_the_smaller_correct_cohort(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        from jeel_portfolio.planner import Plan
        question = "What is the total AUM for high-risk portfolios created after 2023-02-01?"
        sql = "SELECT SUM(total_aum) FROM portfolios WHERE lower(target_risk_level)='high' AND creation_date > :cutoff"
        plan = Plan(tool="sql", sql=sql, parameters=[{"name": "cutoff", "value": "2023-02-01"}])
        monkeypatch.setattr(agent.planner, "plan", lambda *_: plan)
        expected = agent.db.query(sql, {"cutoff": "2023-02-01"}).rows[0][0]
        all_high_risk = agent.db.query("SELECT SUM(total_aum) FROM portfolios WHERE lower(target_risk_level)='high'").rows[0][0]
        assert expected != all_high_risk
        result = agent.answer(question, force_gemini=True)
        assert result["status"] == "ok" and result["rows"] == [[expected]]
    finally:
        agent.close()


def test_total_aum_creation_date_cannot_be_silently_dropped(monkeypatch):
    agent = PortfolioAgent(cache=False)
    try:
        from jeel_portfolio.planner import Plan
        question = "What is the total AUM for high-risk portfolios created after 2023-02-01?"
        incomplete = Plan(tool="sql", sql="SELECT SUM(total_aum) FROM portfolios WHERE lower(target_risk_level)='high'")
        feedback = []

        def fake_plan(_question, _db, previous_error=""):
            feedback.append(previous_error)
            return incomplete

        monkeypatch.setattr(agent.planner, "plan", fake_plan)
        result = agent.answer(question, force_gemini=True)
        assert result["status"] == "error"
        assert "creation-date" in result["message"]
        assert len(feedback) == 2
    finally:
        agent.close()


@pytest.mark.parametrize(("question", "operator", "risk", "status"), [
    ("What is the total AUM for high-risk portfolios created after 2023-02-01?", ">", "high", None),
    ("Total AUM for active medium risk portfolios created before 2024-01-01", "<", "medium", "active"),
    ("Sum of AUM for portfolios with low target risk level created since 2023-02-01", ">=", "low", None),
])
def test_date_filtered_aum_uses_local_recorded_values(question, operator, risk, status):
    agent = PortfolioAgent(cache=False)
    try:
        cutoff = "2024-01-01" if "2024-01-01" in question else "2023-02-01"
        sql = f"SELECT SUM(total_aum) FROM portfolios WHERE lower(target_risk_level)=:risk AND creation_date {operator} :cutoff"
        params = {"risk": risk, "cutoff": cutoff}
        if status:
            sql += " AND lower(status)=:status"
            params["status"] = status
        expected = agent.db.query(sql, params).rows[0][0]
        result = agent.answer(question)
        assert result["status"] == "ok" and result["route"] == "fast_sql"
        assert result["rows"] == [[expected]]
    finally:
        agent.close()


def test_bad_creation_date_is_not_interpreted_as_a_valid_local_filter():
    agent = PortfolioAgent(cache=False)
    try:
        assert agent._fast_plan("Total AUM for high risk portfolios created after 2023-02-30") is None
    finally:
        agent.close()
