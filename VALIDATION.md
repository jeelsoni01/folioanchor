# Validation record

This record separates deterministic local results from live Gemini results. The JSON files under [`reports/`](reports/README.md) preserve each evaluated question, route, result, and latency.

| Check | Result | Interpretation |
| --- | --- | --- |
| Original assessment files | 13 supplied files byte-match the source package | Data, schema, and ground truth were not rewritten |
| Dependency health | `pip check` passes | Pinned environment has no broken requirements |
| Automated regression suite | 168 passed | Includes SQL safety, exposure, routing, provider failures, CLI, and UI |
| Supplied ten questions, local route | 10/10; 1.35 ms median | Deterministic SQL/exposure plans; no API key |
| Nine additional development questions | 9/9 local; 1.24 ms median | Extra known question shapes; no API key |
| Supplied ten questions, Gemini-only route | 10/10 in the current paced live run | Model planning with real API/network latency |
| Nine additional development questions, Gemini-only route | 9/9 in a new complete live run | Model planning beyond the supplied ten |
| Current Gemini provider and AUM smoke | HTTP 200; case 4 passed through Gemini | Confirms key access and model routing after the cleanup |
| Clean-install CI | Windows and Ubuntu × Python 3.11–3.13 | Setup, tests, and both local evaluations on every push |
| Streamlit layout | 390, 768, and 1440 px without page overflow | The desk and a mobile AUM answer were checked in a browser |

The current paced supplied-question Gemini run recorded a 2.54-second median; the nine-question Gemini run recorded 1.62 seconds. An earlier same-day burst repeat passed six cases, then hit a provider rate/quota limit on case 7. That interrupted attempt is not scored as a complete accuracy run. Local answer times are in milliseconds on this machine. These numbers exclude process startup and Streamlit rendering; model latency varies with network and provider conditions. The named question sets were visible during development, so their scores do not measure blind generalization. An unavailable provider call is reported separately from a wrong answer.

## What the tests cover

- Independent reference SQL and CSV exposure checks, including AUM filters, ranked order, bond exclusion, incomplete weights, and both percentage bases.
- Read-only SQL authorization, restricted functions, row/length/execution limits, invalid model plans, and parameter binding.
- Local planner coverage and deliberate fallback when a question adds unsupported modifiers, so filters are not silently dropped.
- Cache invalidation when input data or implementation changes, provider timeout/retry behavior, and no fabricated answer when the provider fails.
- Scope guidance for unrelated, personal-information, and investment-advice prompts; bounded glossary answers for simple financial terms.
- CLI output, Streamlit boot, answer presentation, comparison chart, and local-only interface binding.

## Reproduce

```powershell
python setup_project.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe evaluate.py --output reports\local-evaluation.json
.\.venv\Scripts\python.exe evaluate.py --cases tests\additional_questions.json --output reports\additional-local.json
```

For a local latency sample, run `.\.venv\Scripts\python.exe benchmark.py --runs 1000`. It measures in-process answers and warm cache hits, not Python startup, browser rendering, or live model calls.

After adding a local `GEMINI_API_KEY`, run `.\.venv\Scripts\python.exe diagnose_gemini.py` and then `.\.venv\Scripts\python.exe evaluate.py --gemini-only --delay 15 --output reports\gemini-check.json`. The latter uses quota and can fail for provider reasons without implying that local calculations are wrong.

The [GitHub Actions workflow](.github/workflows/verify.yml) runs clean-install checks without an API key. The GIF is a visual walkthrough, not an accuracy benchmark.
