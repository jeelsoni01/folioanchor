"""Interactive command-line entry point."""

import argparse
import json

from .agent import PortfolioAgent


def show(result: dict):
    print(result.get("message", ""))
    if result.get("rows"):
        print(" | ".join(result["columns"]))
        for row in result["rows"]:
            print(" | ".join(str(value) for value in row))
    for warning in result.get("warnings", []):
        print("Note:", warning)
    print(f"[{result.get('route', 'error')}; {result.get('elapsed_ms', 0):.3f} ms]")


def main():
    parser = argparse.ArgumentParser(description="Ask the portfolio agent")
    parser.add_argument("question", nargs="*", help="Question; omit for interactive mode")
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    agent = PortfolioAgent(cache=not args.no_cache)
    try:
        if args.question:
            result = agent.answer(" ".join(args.question))
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                show(result)
            raise SystemExit(0 if result["status"] == "ok" else 1)
        print("Portfolio agent. Ask a question, or type quit.")
        while True:
            try:
                question = input("\nAsk> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if question.casefold() in ("quit", "exit", "q"):
                break
            if question:
                result = agent.answer(question)
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    show(result)
    finally:
        agent.close()


if __name__ == "__main__":
    main()
