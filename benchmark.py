"""Measure in-process local and warm-cache latency; excludes UI/CLI startup."""

import argparse
import statistics
import time

from jeel_portfolio.agent import PortfolioAgent


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, int((len(ordered)-1)*p))]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1000)
    args = parser.parse_args()
    question = "How many portfolios do we have in total?"
    uncached = PortfolioAgent(cache=False)
    try:
        first = uncached.answer(question)
    finally:
        uncached.close()
    agent = PortfolioAgent()
    try:
        agent.answer(question)
        samples = []
        for _ in range(max(1, args.runs)):
            begin = time.perf_counter_ns()
            answer = agent.answer(question)
            samples.append((time.perf_counter_ns()-begin)/1000)
        print(f"Uncached local result: {first['route']}, {first['elapsed_ms']:.3f} ms")
        print(f"Warm in-process cache: median {statistics.median(samples):.1f} microseconds; p95 {percentile(samples,.95):.1f} microseconds ({len(samples)} runs)")
        print("Excludes Python startup, Streamlit rendering, and network; new Gemini questions are much slower.")
    finally:
        agent.close()
