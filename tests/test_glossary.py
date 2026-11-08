import pytest
from streamlit.testing.v1 import AppTest

from jeel_portfolio.agent import PortfolioAgent
from jeel_portfolio.database import ROOT


@pytest.mark.parametrize(("question", "term"), [
    ("what is portfolio?", "portfolio"),
    ("What is a portfolio?", "portfolio"),
    ("What does portfolio mean?", "portfolio"),
    ("Define investment portfolio", "investment portfolio"),
    ("What is a holding?", "holding"),
    ("What is AUM?", "aum"),
    ("Explain assets under management", "assets under management"),
    ("What is sector exposure?", "sector exposure"),
    ("What is cost basis?", "cost basis"),
    ("What is diversification?", "diversification"),
])
def test_simple_financial_definitions_are_local_without_provider(monkeypatch, question, term):
    agent = PortfolioAgent(cache=False)
    try:
        def must_not_call(*_args, **_kwargs):
            raise AssertionError("Gemini was called for a local definition")

        monkeypatch.setattr(agent.planner, "plan", must_not_call)
        result = agent.answer(question, force_gemini=True)
        assert result["status"] == "ok"
        assert result["route"] == "local_glossary"
        assert result["rows"][0][0] == term
        assert result["message"]
    finally:
        agent.close()


@pytest.mark.parametrize("question", [
    "What is the total AUM for high-risk portfolios?",
    "What is the portfolio with the highest AUM?",
    "What is the sector exposure for Tech Innovation Fund?",
    "What is the current price of AAPL?",
])
def test_data_questions_are_not_mistaken_for_definitions(question):
    assert PortfolioAgent._glossary_definition(question) is None


def test_streamlit_explains_portfolio_without_provider_error():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    app.text_input[0].set_value("what is portfolio?").run()
    app.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert any("A portfolio is a group of investments" in item.value for item in app.info)
