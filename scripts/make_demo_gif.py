"""Makes docs/img/otis-demo.gif: a question typed into the Otis page and the answer appearing.

The page is docs/img/demo/frame.html, drawn for one tick at a time. Each tick is shot with headless
Edge or Chrome and the shots are joined into a GIF with ffmpeg. The content is a real saved answer
from the dev run of 2 November 2026 (vr-005), so nothing in the picture is invented, and the frame
says it is a recording and the interface a mockup. No API call is made.

Needs Edge or Chrome and ffmpeg on the path.

Usage:
    python scripts/make_demo_gif.py
"""

import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAME = ROOT / "docs" / "img" / "demo" / "frame.html"
OUT = ROOT / "docs" / "img" / "otis-demo.gif"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SIZE = (1000, 740)
WORKERS = 4


def browser() -> str:
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    if Path(EDGE).exists():
        return EDGE
    raise SystemExit("No Chromium browser found.")


def run_browser(exe: str, profile: Path, *args: str) -> subprocess.CompletedProcess:
    command = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               f"--user-data-dir={profile}", *args]  # fmt: skip
    return subprocess.run(  # noqa: S603 - a fixed browser path and a file URL we built
        command, capture_output=True, text=True, timeout=90, check=False
    )


def total_ticks(exe: str, work: Path) -> tuple[int, int]:
    done = run_browser(exe, work / "p0", "--dump-dom", FRAME.as_uri() + "#tick=0")
    total = re.search(r'data-total="(\d+)"', done.stdout)
    millis = re.search(r'data-tick-ms="(\d+)"', done.stdout)
    if not total or not millis:
        raise SystemExit("The frame page did not report its length.")
    return int(total.group(1)), int(millis.group(1))


def shoot(exe: str, work: Path, tick: int) -> Path:
    target = work / f"f{tick:04d}.png"
    run_browser(
        exe, work / f"p{tick % WORKERS}x{tick}", f"--screenshot={target}",
        f"--window-size={SIZE[0]},{SIZE[1]}", "--force-device-scale-factor=1",
        FRAME.as_uri() + f"#tick={tick}",
    )  # fmt: skip
    if not target.exists():
        raise SystemExit(f"No screenshot for tick {tick}.")
    return target


def main() -> int:
    exe = browser()
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        total, millis = total_ticks(exe, work)
        print(f"{total} ticks of {millis} ms", flush=True)
        with ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(lambda tick: shoot(exe, work, tick), range(total)))
        fps = 1000 / millis
        palette = work / "palette.png"
        pattern = str(work / "f%04d.png")
        base = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", pattern]
        subprocess.run([*base, "-vf", "palettegen=stats_mode=diff", str(palette)], check=True)  # noqa: S603
        subprocess.run(  # noqa: S603
            [*base, "-i", str(palette), "-lavfi",
             "paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", "-loop", "0", str(OUT)],
            check=True,
        )  # fmt: skip
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
