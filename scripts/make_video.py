#!/usr/bin/env python3
"""Render docs/demo.mp4 from the REAL output of scripts/run_demo.py.

Terminal-style rendering (Pillow frames -> ffmpeg). Reproducible:
    python scripts/run_demo.py > /tmp/demo_output.txt
    python scripts/make_video.py            # writes docs/demo.mp4

Requires: pillow, ffmpeg on PATH.
"""
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEMO_TXT = Path("/tmp/demo_output.txt")
FRAMES = Path("/tmp/verba_frames")
OUT = ROOT / "docs" / "demo.mp4"

W, H = 1280, 720
FPS = 30
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT = ImageFont.truetype(FONT_PATH, 21)
FONT_SM = ImageFont.truetype(FONT_PATH, 18)
LINE_H = 27
MARGIN = 36
MAX_LINES = (H - 2 * MARGIN - 70) // LINE_H
WRAP = 100

C_BG = (13, 17, 23)
C_DIM = (139, 148, 158)
C_CALLER = (121, 192, 255)
C_AGENT = (86, 211, 100)
C_OWNER = (210, 168, 255)
C_BLOCK = (248, 81, 73)
C_NAIVE = (227, 179, 65)


def classify(line: str):
    s = line.strip()
    if s.startswith("=") or s.startswith("ACT ") or s.startswith("DONE"):
        return C_DIM, True
    if s.startswith("CALLER"):
        return C_CALLER, False
    if s.startswith(("AGENT", "VERBA")):
        return C_AGENT, False
    if s.startswith("OWNER"):
        return C_OWNER, False
    if "[validator blocked" in s or "[guardrail:" in s:
        return C_BLOCK, False
    if s.startswith(("Model facts", "(Rao", "hours", "Same minute", "The Dec 19")):
        return C_NAIVE, False
    return C_DIM, False


def wrap_line(line: str):
    if not line.strip():
        return [("", C_DIM)]
    color, _ = classify(line)
    chunks = textwrap.wrap(line, WRAP, subsequent_indent="    ",
                           break_long_words=False, break_on_hyphens=False) or [""]
    return [(c, color) for c in chunks]


def load_script():
    raw = DEMO_TXT.read_text().splitlines()
    out = []
    for line in raw:
        out.extend(wrap_line(line.rstrip()))
    return out


def draw_frame(visible, outfile, cursor=""):
    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 34], fill=(22, 27, 34))
    d.text((MARGIN, 7), "verba - signature demo (python scripts/run_demo.py)",
           font=FONT_SM, fill=C_DIM)
    y = H - MARGIN - LINE_H * len(visible) - 20
    for text, color in visible:
        d.text((MARGIN, y), text, font=FONT, fill=color)
        y += LINE_H
    if cursor:
        d.text((MARGIN, y), cursor, font=FONT, fill=C_AGENT)
    img.save(outfile)


def title_card(path_for, lines, seconds):
    n = int(FPS * seconds)
    for i in range(n):
        img = Image.new("RGB", (W, H), C_BG)
        d = ImageDraw.Draw(img)
        y = H // 2 - (len(lines) * 34) // 2
        for text, color, font in lines:
            w = d.textlength(text, font=font)
            d.text(((W - w) / 2, y), text, font=font, fill=color)
            y += 34
        img.save(path_for(i))
    return n


def main():
    FRAMES.mkdir(exist_ok=True)
    for f in FRAMES.glob("*.png"):
        f.unlink()

    script = load_script()
    idx = 0

    def frame_path(i):
        return str(FRAMES / f"{i:05d}.png")

    # title card
    idx += title_card(lambda i: frame_path(i), [
        ("Verba", C_AGENT, ImageFont.truetype(FONT_PATH, 44)),
        ("an SMB voice agent whose answers are validated", C_DIM, FONT),
        ("against a formal business ontology before they are spoken", C_DIM, FONT),
        ("", C_DIM, FONT),
        ("signature demo - real output of scripts/run_demo.py", C_NAIVE, FONT_SM),
    ], 2.6)
    base = idx

    visible: list = []
    fidx = base
    for text, color in script:
        visible.append((text, color))
        visible = visible[-MAX_LINES:]
        is_banner = text.strip().startswith(("=", "ACT", "DONE"))
        hold = FPS * 2 if is_banner else 6
        for _ in range(hold):
            draw_frame(visible, frame_path(fidx))
            fidx += 1

    # end card
    end_start = fidx
    idx_end = title_card(lambda i: str(FRAMES / f"end_{i:05d}.png"), [
        ("naive draft 0/5  -  validated answer 5/5", C_NAIVE, FONT),
        ("github.com/aneesh2411/verba", C_CALLER, FONT),
        ("aneesh2411.github.io/verba", C_CALLER, FONT),
    ], 2.6)
    for i in range(idx_end):
        (FRAMES / f"end_{i:05d}.png").rename(frame_path(end_start + i))
    fidx = end_start + idx_end

    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(FRAMES / "%05d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
        "-movflags", "+faststart", str(OUT),
    ], check=True, capture_output=True)
    print(f"wrote {OUT} ({fidx / FPS:.0f}s, {fidx} frames)")


if __name__ == "__main__":
    main()
