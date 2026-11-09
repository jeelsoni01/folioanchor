# Demo GIF source

`../demo.gif` is a silent 18.2-second walkthrough for GitHub. The five beats follow the [Brag](https://github.com/latent-spaces/brag) skill's product-specific hook → interaction → result → evidence structure, adapted to GitHub's GIF playback. Every screenshot in `frames/` was captured from the running local Streamlit app against the supplied sample dataset. Text in the GIF header describes what each captured screen shows; it is not an AI-generated answer.

To rebuild the same GIF after setup:

```powershell
.\.venv\Scripts\python.exe docs\demo\build_gif.py
```

For a UI change, recapture the four PNG screenshots at a 1440×900 browser viewport; the first screenshot supplies two scenes. Keep the question, answer, and visible data aligned; never place a key, `.env`, or private user information in a frame. The GIF contains no audio, as GitHub README images autoplay without sound.
