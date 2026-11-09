from streamlit.testing.v1 import AppTest

from portfolio_agent.agent import PortfolioAgent
from portfolio_agent.database import ROOT
from portfolio_agent.presentation import present_answer


QUESTION = "Which active high-risk portfolio has the highest Technology exposure?"


def test_hybrid_answer_names_the_winner_and_preserves_full_comparison():
    agent = PortfolioAgent(cache=False)
    try:
        result = agent.answer(QUESTION)
        assert result["status"] == "ok"
        assert result["rows"] == [["Tech Innovation Fund", 100.0]]
        assert len(result["evidence"]["comparison_rows"]) == 4
        lead, context = present_answer(result)
        assert "Tech Innovation Fund" in lead and "100%" in lead
        assert "Compared 4" in context
        assert result["evidence"]["comparison_rows"][0] == result["rows"][0]
    finally:
        agent.close()


def test_streamlit_shows_full_comparison_without_a_single_bar_chart():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    app.text_input[0].set_value(QUESTION).run()
    app.button[0].click().run()
    assert not app.exception
    assert not app.error
    markup = "\n".join(item.value for item in app.markdown)
    assert "Tech Innovation Fund has the highest Technology exposure at 100%" in markup
    assert "Compared 4 recorded portfolios" in markup
    assert "Technology exposure across 4 portfolios" in markup
    assert "comparison-row" in markup


def test_risk_filtered_aum_answer_names_cohort_and_unit_limit():
    agent = PortfolioAgent(cache=False)
    try:
        result = agent.answer(
            "What is the total Assets Under Management (AUM) for portfolios with high target risk level?"
        )
        lead, context = present_answer(result)
        assert lead == "Portfolios with high target risk have 85,000,000 in recorded AUM."
        assert "no currency is specified" in context
    finally:
        agent.close()
