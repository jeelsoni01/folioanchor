import json
import subprocess
import sys
import tomllib

from streamlit.testing.v1 import AppTest

from portfolio_agent.database import ROOT


def test_cli_returns_structured_answer_without_provider():
    completed = subprocess.run(
        [sys.executable, "-m", "portfolio_agent", "--no-cache", "--json",
         "How many portfolios do we have in total?"],
        cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "ok" and result["rows"] == [[13]]
    assert result["route"] == "fast_sql"


def test_streamlit_interface_boots_without_provider_call():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 3
    assert len(app.dataframe) >= 3


def test_local_demo_is_not_bound_to_the_network():
    settings = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert settings["server"]["address"] == "127.0.0.1"
