"""Build the README walkthrough from captured, unedited Streamlit screens.

Run from any directory with the project's Python environment:
    python docs/demo/build_gif.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "demo.gif"
WIDTH = 1120
SCREEN_HEIGHT = 650
HEADER_HEIGHT = 58
NAVY = "#14223f"
ACCENT = "#52c6cd"

SCENES = [
    ("01-question.png", 0, "Ask the desk", "A real question over the supplied portfolio snapshot", 2800),
    ("01-question.png", 245, "Type a portfolio question", "The same interface accepts new questions", 2600),
    ("02-exposure.png", 170, "See the result and comparison", "Technology exposure across the recorded portfolios", 4200),
    ("03-aum.png", 145, "Check recorded AUM", "The high-risk cohort is calculated from the portfolio table", 3300),
    ("04-explorer.png", 0, "Inspect the positions", "Sector weights and holdings remain visible to the reviewer", 3300),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def render_scene(filename: str, top: int, title: str, detail: str) -> Image.Image:
    screenshot = Image.open(HERE / "frames" / filename).convert("RGB")
    left = (screenshot.width - WIDTH) // 2
    top = min(top, screenshot.height - SCREEN_HEIGHT)
    screen = screenshot.crop((left, top, left + WIDTH, top + SCREEN_HEIGHT))
    image = Image.new("RGB", (WIDTH, HEADER_HEIGHT + SCREEN_HEIGHT), NAVY)
    image.paste(screen, (0, HEADER_HEIGHT))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, HEADER_HEIGHT - 3, WIDTH, HEADER_HEIGHT), fill=ACCENT)
    draw.text((20, 12), title, font=font(23, True), fill="white")
    detail_font = font(14)
    detail_width = draw.textlength(detail, font=detail_font)
    draw.text((WIDTH - 20 - detail_width, 20), detail, font=detail_font, fill="#d0e1f1")
    return image


def main() -> None:
    scenes = [render_scene(*scene[:4]) for scene in SCENES]
    images: list[Image.Image] = []
    durations: list[int] = []
    for index, (scene, config) in enumerate(zip(scenes, SCENES)):
        images.append(scene)
        durations.append(config[4])
        if index < len(scenes) - 1:
            following = scenes[index + 1]
            for step in range(1, 5):
                images.append(Image.blend(scene, following, step / 5))
                durations.append(100)
    # The final frame flows gently back into the opening frame when GitHub loops it.
    for step in range(1, 5):
        images.append(Image.blend(scenes[-1], scenes[0], step / 5))
        durations.append(100)

    palette_frames = [
        frame.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        for frame in images
    ]
    palette_frames[0].save(
        OUT,
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=True,
    )
    print(f"Wrote {OUT} ({sum(durations) / 1000:.1f}s, {len(images)} frames)")


if __name__ == "__main__":
    main()
