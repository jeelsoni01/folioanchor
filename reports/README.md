# Retained evaluation evidence

| File | Meaning |
| --- | --- |
| `local-evaluation.json` | Supplied ten-question evaluation through the normal local-first route |
| `additional-local.json` | Nine additional development questions through the normal route |
| `gemini-only.json` | Complete live Gemini-only run over the supplied ten questions |
| `additional-gemini.json` | Complete live Gemini-only run over nine additional development questions |

The first two reports test deterministic local planning and calculations; they are **not** evidence of Gemini accuracy. The two Gemini reports bypass local planning and record provider latency. All cases were visible during development and are not a blind benchmark. A provider outage is tracked as unavailable rather than an accuracy miss.

Regenerate the local reports with the commands in the root [README](../README.md#verify-the-project). A fresh Gemini run requires your own API key; write it to a new ignored report such as `reports/gemini-check.json`, leaving the retained evidence intact.
