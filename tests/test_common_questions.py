"""Question-shape checks beyond either supplied evaluation set."""

import pytest

from portfolio_agent.agent import PortfolioAgent
from portfolio_agent.database import DataError


@pytest.mark.parametrize(("question", "reference"), [
    ("How many portfolios have status Active?", "SELECT COUNT(*) FROM portfolios WHERE status='Active'"),
    ("Number of securities classified as stocks?", "SELECT COUNT(*) FROM securities WHERE asset_type='Stock'"),
    ("Show active portfolio names and AUM from highest AUM to lowest.",
     "SELECT portfolio_name,total_aum FROM portfolios WHERE status='Active' ORDER BY total_aum DESC"),
    ("List portfolios with AUM greater than 25 million.",
     "SELECT portfolio_name FROM portfolios WHERE total_aum>25000000 ORDER BY total_aum DESC"),
    ("Show the five funds with highest AUM.",
     "SELECT portfolio_name,total_aum FROM portfolios ORDER BY total_aum DESC LIMIT 5"),
    ("Which portfolios have no performance records?",
     "SELECT p.portfolio_name FROM portfolios p LEFT JOIN portfolio_performance pp "
     "ON p.portfolio_id=pp.portfolio_id WHERE pp.portfolio_id IS NULL ORDER BY p.portfolio_name"),
    ("Which portfolios hold both AAPL and MSFT, and what is their combined recorded weight as a percentage, highest first?",
     "SELECT p.portfolio_name,ROUND(SUM(h.current_weight)*100,2) FROM portfolios p "
     "JOIN holdings h USING(portfolio_id) JOIN securities s USING(security_id) "
     "WHERE s.symbol IN ('AAPL','MSFT') GROUP BY p.portfolio_id "
     "HAVING COUNT(DISTINCT s.symbol)=2 ORDER BY 2 DESC"),
])
def test_common_questions_agree_with_independent_sql(question, reference):
    agent = PortfolioAgent(cache=False)
    try:
        result = agent.answer(question)
        expected = agent.db.query(reference)
        assert result["route"] == "fast_sql"
        assert result["status"] == "ok"
        assert result["rows"] == [list(row) for row in expected.rows]
    finally:
        agent.close()


@pytest.mark.parametrize(("question", "name", "basis"), [
    ("Show the sector allocation of ESG Sustainable Fund.", "ESG Sustainable Fund", "portfolio"),
    ("How is the Balanced Portfolio distributed across sectors?", "Balanced Portfolio", "portfolio"),
    ("What is the equity-only sector exposure for Growth Equity Fund?", "Growth Equity Fund", "equity"),
])
def test_common_exposure_uses_recorded_fund_and_basis(question, name, basis):
    agent = PortfolioAgent(cache=False)
    try:
        result = agent.answer(question)
        assert result["route"] == "fast_exposure"
        assert result["evidence"]["portfolio"] == name
        assert result["evidence"]["basis"] == basis
    finally:
        agent.close()


@pytest.mark.parametrize("question", [
    "How many securities are bonds purchased after 2024?",
    "List portfolios with AUM above 25 million and high risk.",
    "Show the five active funds with highest AUM.",
    "What is the sector exposure of Balanced Portfolio as of last month?",
    "Which portfolios have no performance records since 2024?",
    "How many passive funds hold AAPL?",
])
def test_extra_filters_do_not_get_silently_dropped(question):
    agent = PortfolioAgent(cache=False)
    try:
        assert agent._fast_plan(question) is None
    finally:
        agent.close()


@pytest.mark.parametrize(("question", "bad_sql", "required"), [
    ("How many Passive funds are there?", "SELECT COUNT(*) FROM portfolios", "status"),
    ("List high-risk funds", "SELECT portfolio_name FROM portfolios", "target_risk_level"),
    ("Which portfolios were created after 2023-01-01?", "SELECT portfolio_name FROM portfolios", "creation_date"),
    ("Show funds with AUM above 20 million", "SELECT portfolio_name FROM portfolios", "total_aum"),
])
def test_model_sql_cannot_drop_requested_filters(question, bad_sql, required):
    with pytest.raises(DataError, match=required):
        PortfolioAgent._validate_sql_plan(question, bad_sql)
