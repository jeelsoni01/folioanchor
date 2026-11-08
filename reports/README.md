# Reproducible checks

These JSON files record development checks; the repository workflow reruns the local ones on each push and pull request. `evaluation-current.json` is the supplied ten-question set. `shardul-extra-local.json` is the eight additional questions from the comparison repository; `holdout-local-new.json` is another nine-question development set. All three use the local SQL/exposure routes, so their scores do not measure Gemini accuracy.

`gemini-current-rerun.json` is a complete 10/10 live model-planning run. `gemini-current-interrupted.json` and `shardul-extra-gemini-current-interrupted.json` show separate provider timeouts; their unrun cases have no accuracy result. No API key is stored in these reports.

To regenerate the main local check from the repository root:

```powershell
.\.venv\Scripts\python.exe evaluate.py --output reports\evaluation-current.json
.\.venv\Scripts\python.exe evaluate.py --cases tests\shardul_extra_questions.json --output reports\shardul-extra-local.json
.\.venv\Scripts\python.exe evaluate.py --cases tests\holdout_questions.json --output reports\holdout-local-new.json
```
