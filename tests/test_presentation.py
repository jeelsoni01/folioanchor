from streamlit.testing.v1 import AppTest

from jeel_portfolio.agent import PortfolioAgent
from jeel_portfolio.database import ROOT
from jeel_portfolio.presentation import present_answer


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
