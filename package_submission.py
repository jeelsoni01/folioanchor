"""Create a clean source package without local secrets or environments."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "jeel-portfolio-agent-submission.zip"
FILES = (
    ".env.example", ".gitignore", ".streamlit/config.toml", ".github/workflows/verify.yml",
    "README.md", "VALIDATION.md", "THIRD_PARTY_NOTICES.md", "start.ps1",
    "requirements.txt", "requirements-lock.txt", "database_schema.sql",
    "ground_truth_dataset.json", "app.py", "evaluate.py", "benchmark.py", "diagnose_gemini.py",
    "setup_project.py", "package_submission.py",
    "reports/evaluation.json", "reports/evaluation-312.json", "reports/gemini-evaluation.json",
    "reports/holdout-gemini.json", "reports/gemini-aum-recheck.json",
    "reports/archive/gemini-first-pass.json",
    "reports/evaluation-current.json", "reports/evaluation-current-312.json",
    "reports/shardul-extra-local.json", "reports/holdout-local-new.json",
    "reports/gemini-current-rerun.json", "reports/gemini-current-interrupted.json",
    "reports/shardul-extra-gemini-current-interrupted.json",
)
DIRECTORIES = ("assets", "data", "brief", "jeel_portfolio", "tests")


def main():
    selected = [ROOT / name for name in FILES]
    for dirname in DIRECTORIES:
        selected.extend(path for path in (ROOT / dirname).rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    selected = sorted(set(selected))
    for path in selected:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.name == ".env" or any(part.startswith(".venv") for part in path.parts):
            raise ValueError("Local secret or environment in package list")
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as bundle:
        for path in selected:
            bundle.write(path, Path(ROOT.name) / path.relative_to(ROOT))
    with ZipFile(OUTPUT) as bundle:
        names = bundle.namelist()
        assert bundle.testzip() is None
        assert not any(name.endswith("/.env") or "/.venv" in name for name in names)
    print(f"Created {OUTPUT} with {len(selected)} files; no .env or virtual environment included.")


if __name__ == "__main__":
    main()
