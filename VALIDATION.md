# Validation record

Observed on Windows with Python 3.13 and `google-genai` 2.34.0. Reports are in `reports/` locally. This file separates local execution from model accuracy.

| Check | Result |
|---|---|
| Original assessment materials | All 13 supplied files byte-match the original folder |
| Dependencies | Installed in `.venv`; `pip check` reports no broken requirements |
| Automated tests | 167 passed under Python 3.12 and 3.13 |
| Supplied evaluation, normal hybrid route | 10/10 on both Python versions; about 1.8 ms median in the latest runs |
| Shardul's eight extra questions | 8/8 through local plans; 1.23 ms median |
| Jeel's nine additional questions | 9/9 through local plans; 1.07 ms median |
| Warm cache microbenchmark | 8.4 microseconds median, 15.0 microseconds p95 over 5,000 standalone calls |
| Streamlit smoke | Three tabs, three tables, no app exceptions |
| Unseen Gemini question | Correct SQL answer for largest AUM fund, about 11 seconds in the first successful probe |
| Gemini-only first full run | 7/10 passed; three defects identified and preserved under `reports/archive/` |
| Gemini-only supplied runs | Three earlier and one current complete 10/10 passes; current median 2.68 seconds |
| Additional nine Gemini questions | 9/9 passed; 1.92-second median |
| Direct authenticated key check | HTTP 200 for model access and minimal generation; a candidate was returned |

The first Gemini-only misses were: extra unrequested columns on case 3, missing reference fields on case 5, and weight-based hybrid selected for a market-value question on case 7. The evaluator projects explicitly named requested columns while rejecting missing fields. The planner specifies the holdings fields and market-value route. Named-sector market-value results are checked against the supplied holdings and prices, including cohort and denominator, and repaired once when needed. A subsequent full run passed all ten.

The nine additional questions exposed two more mistakes: Passive was mapped to `strategy_type` instead of `status`, and combined holding weights were returned as fractions instead of percentages. Those semantics are now checked and the full additional run passed 9/9. AUM totals also have a dedicated aggregate-and-filter check; the targeted Gemini AUM recheck passed.

Provider unavailability is reported separately from wrong answers. The live evaluator stops after an unavailable result and writes a separate `-interrupted.json` report, preserving any completed score. Its wall limit defaults to 60 seconds and can be adjusted with `GEMINI_TIMEOUT_SECONDS` in `.env`. A late model plan can be reused when the same question is retried in the same agent process. Known local routes and cached results remain available without Gemini.

Guarded SQL rejects writes, hidden tables, unsupported functions, result overflows, and constant-only answers that do not read the supplied snapshot. The regression suite includes injection attempts, incomplete weights, bond exclusion, ambiguous names, hybrid cohort validation, AUM aggregation, market-value verification, model-plan correction, cache invalidation, provider transport retry, timeout behavior, CLI, and UI boot. No source or report file contained the saved key in the final scan.

The local fast router was audited with questions containing extra time, price, status, and geography filters. It now declines unsupported modifiers instead of returning an incomplete fast answer. Those questions use Gemini planning and remain subject to provider availability and plan validation. A targeted test confirms that a correctly date-filtered AUM result is accepted, while a plan that drops the requested creation-date filter is rejected.

The expanded regression suite checks every portfolio's stock-sector exposure against a separate CSV calculation at both percentage bases, 18 unsafe or ungrounded SQL shapes, nine invalid plan shapes, malformed source files, the repeated uncached Gemini question path, out-of-scope prompts, and the existing CLI/UI and evaluator checks. The planner now clears a consumed late/model response so a repeated uncached question starts a new request. CSV import errors are reported as data errors. The fixed-delay timeout test was replaced with a worker join after it proved timing-sensitive under Python 3.12.

An additional AUM question with an ISO creation-date filter is handled locally through a parameterized query; it returned 28,000,000 in about 3 ms. Its prior Gemini-only attempt timed out after 60 seconds, so no model accuracy is inferred from that attempt. A user's off-topic question, “tell me who is jeel,” previously waited for Gemini and timed out. The scope guard now returns a clarification in about 3 ms without a model call. Streamlit displays it as information and hides any stale answer from the previous question. The supplied 10 questions still pass after the guard was added.

A later user question, “what is portfolio?”, exposed a different gap: an in-scope definition request still waited on Gemini. The local glossary now answers exact, simple definitions for portfolio, holding, AUM, sector exposure and related terms; the observed CLI answer took 0.715 ms in-process. Fifteen regression cases verify glossary variants, prevent misrouting data questions, and check the Streamlit explanation. The glossary is intentionally bounded: unfamiliar financial concepts still receive ordinary scope/model handling rather than invented definitions.

The local Streamlit demo is bound to `127.0.0.1` by packaged configuration. A prior default start advertised a network-facing URL; after the change, Streamlit reported `Uvicorn server started on 127.0.0.1:8501`. The interface has no login and should not be exposed to a network without separate access controls.

## Follow-up breadth and reproducibility work

Shardul's eight published extra questions now pass 8/8 through a conservative local planner. Nine other development questions pass 9/9 locally. The planner handles question shapes rather than hardcoded result values; all counts, AUM rankings, dates and weights come from guarded SQL or the existing exposure calculator. Six regression questions with extra filters deliberately bypass the local planner. Seven independent SQL comparisons and three exposure checks cover paraphrases beyond the two evaluation sets. These question sets are development cases, not a blind generalization benchmark.

The setup script now installs `requirements-lock.txt`, checks the interpreter, preserves an existing `.env`, and reports setup failures. The NumPy pin uses a Python 3.11 marker consistent with the reference project's tested pin. An optional `start.ps1` and a six-job GitHub Actions matrix for Windows/Ubuntu with Python 3.11–3.13 were added; the workflow has not run because no GitHub repository has been published yet. `setup_project.py` and `pip check` succeeded in the existing Python 3.13 environment. Direct PyPI wheel downloads still prevent a fresh local Python 3.12 install, so that claim remains unverified.

The Gemini planner now explicitly handles shortened unique portfolio names and latest recorded dates, uses temperature zero, and labels missing-key, timeout, authentication, quota, connection, and server failures separately. One current full Gemini-only attempt passed cases 1 and 2, then case 3 timed out at 60 seconds. A retry of case 3 passed in 42.38 seconds; the next complete supplied run passed 10/10 with a 2.68-second median. A separate live attempt on Shardul's eight extra questions timed out on its first request, so it provides no model-accuracy score. The provider remains latency-variable.

The Streamlit result now places the fund and percentage in a bold answer card, explains the denominator, and moves route/timing into the evidence expander. Hybrid evidence retains the full ranked cohort even when the requested answer is only the top fund. The UI displays a labelled comparison of all four eligible funds; it suppresses a one-bar chart. The same proportional bars are used for multi-sector allocations in the portfolio explorer. Streamlit AppTest checks the result content and absence of UI exceptions.

To rerun validation:

```powershell
cd 'D:\PL Capital\jeel-portfolio-agent'
.\.venv\Scripts\python.exe evaluate.py --gemini-only --output reports\gemini-evaluation.json
.\.venv\Scripts\python.exe evaluate.py --gemini-only --cases tests\holdout_questions.json --output reports\holdout-gemini.json
.\.venv\Scripts\python.exe diagnose_gemini.py
```

Python 3.12 source compatibility was verified with an existing local Python 3.12 environment: 167/167 tests and 10/10 local evaluation cases passed. The project's own `.venv312` is still incomplete because direct PyPI downloads of NumPy/pandas timed out, so a **fresh install of this lock file under 3.12 is not yet verified**. Python 3.13 passed the same checks in the project's installed environment, and `setup_project.py` with the pinned lock file completed there. A six-job GitHub Actions workflow is included but has not run without a published repository. No local macOS/Linux run has been performed. A complete live Gemini-only 10/10 run is recorded for the current model-planning code.
