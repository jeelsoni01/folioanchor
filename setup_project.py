"""One-command, pinned local setup; preserves any existing key."""

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    target = root / ".venv"
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 1
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(target)
        version = subprocess.run(
            [str(python), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if tuple(map(int, version.split("."))) < (3, 11):
            print(f"Existing .venv uses Python {version}; use Python 3.11 or newer.", file=sys.stderr)
            return 1
        requested = f"{sys.version_info.major}.{sys.version_info.minor}"
        if version != requested:
            print(f"Existing .venv uses Python {version}, but setup was started with Python {requested}.", file=sys.stderr)
            print("Use the matching interpreter or move the old .venv aside before rerunning setup.", file=sys.stderr)
            return 1
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(root / "requirements-lock.txt")], check=True)
        subprocess.run([str(python), "-m", "pip", "check"], check=True)
        if not (root / ".env").exists():
            shutil.copyfile(root / ".env.example", root / ".env")
        command = r".\.venv\Scripts\python.exe" if os.name == "nt" else "./.venv/bin/python"
        print("Setup complete. Existing .env, if present, was preserved.")
        print("Set GEMINI_API_KEY in .env for model-planned questions.")
        print(f"CLI: {command} -m portfolio_agent")
        print(f"Optional UI: {command} -m streamlit run app.py")
        return 0
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        print("Check Python and network access, then rerun setup_project.py.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
