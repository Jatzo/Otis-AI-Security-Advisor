"""Makes docs/img/replay-demo.gif: the real replay page, shown on three saved questions.

The page in docs/demo/ is served on a local port and shot with headless Edge or Chrome at a height
tall enough to hold the whole page. ffmpeg then moves a window over each shot and joins the scenes
into a GIF. Nothing in the picture is drawn by this script: it is the page as it renders. No API
call is made, and the page makes no request except for its own data file.

Needs Edge or Chrome and ffmpeg on the path.

Usage:
    python scripts/make_replay_gif.py
"""

import functools
import http.server
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "docs" / "demo"
OUT = ROOT / "docs" / "img" / "replay-demo.gif"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
WIDTH, VIEW, TALL = 1400, 800, 2900  # the window width, the part of the page shown, the shot height
# 12.5 frames a second is a whole 8 hundredths each, the unit a GIF counts in, so the scroll runs
# evenly.
FPS, OUT_WIDTH, COLOURS = 12.5, 760, 48
CARDS, RECORDS = 330, 1000  # how far down the three result cards and the list of records start
# A question the Phase 6 checker lets through, one it still refuses, and one the model declined.
# Each scene is (question, waypoints), and a waypoint is (seconds, how far down the page).
SCENES = (
    ("dg-003", ((0, 0), (1.6, 0), (2.6, CARDS), (5.2, CARDS), (6.4, RECORDS), (7.4, RECORDS))),
    ("lk-001", ((0, CARDS), (3.2, CARDS))),
    ("ab-001", ((0, CARDS), (3.2, CARDS))),
)


def browser() -> str:
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    if Path(EDGE).exists():
        return EDGE
    raise SystemExit("No Chromium browser found.")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def serve() -> http.server.ThreadingHTTPServer:
    handler = functools.partial(Quiet, directory=str(DEMO))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def shoot(exe: str, work: Path, port: int, question: str) -> Path:
    target = work / f"{question}.png"
    command = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               f"--user-data-dir={work / ('p-' + question)}", f"--window-size={WIDTH},{TALL}",
               "--virtual-time-budget=5000", f"--screenshot={target}",
               f"http://127.0.0.1:{port}/#{question}"]  # fmt: skip
    subprocess.run(  # noqa: S603 - a fixed browser path and a local address we built
        command, capture_output=True, text=True, timeout=120, check=False
    )
    if not target.exists():
        raise SystemExit(f"The browser made no picture for {question}.")
    return target


def scroll(waypoints: tuple) -> str:
    """An ffmpeg expression for how far down the window is at time t: it eases from one waypoint to
    the next and holds at the last."""
    expression = str(waypoints[-1][1])
    for (start, y0), (end, y1) in reversed(list(zip(waypoints, waypoints[1:], strict=False))):
        if y0 == y1:
            step = str(y0)
        else:
            u = f"(t-{start})/{end - start}"
            step = f"{y0}+({y1}-{y0})*({u})*({u})*(3-2*({u}))"
        expression = f"if(lt(t,{end}),{step},{expression})"
    return expression


def main() -> int:
    exe = browser()
    server = serve()
    port = server.server_address[1]
    try:
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            inputs, graph, ends = [], [], []
            for index, (question, waypoints) in enumerate(SCENES):
                shot = shoot(exe, work, port, question)
                seconds = waypoints[-1][0]
                inputs += [
                    "-loop",
                    "1",
                    "-framerate",
                    str(FPS),
                    "-t",
                    str(seconds),
                    "-i",
                    str(shot),
                ]
                graph.append(
                    f"[{index}:v]crop={WIDTH}:{VIEW}:0:'{scroll(waypoints)}',fps={FPS},"
                    f"scale={OUT_WIDTH}:-1:flags=lanczos[v{index}]"
                )
                ends.append(f"[v{index}]")
            graph.append(
                f"{''.join(ends)}concat=n={len(SCENES)}:v=1[all];[all]split[a][b];"
                f"[a]palettegen=max_colors={COLOURS}[p];"
                "[b][p]paletteuse=dither=none:diff_mode=rectangle"
            )
            OUT.parent.mkdir(parents=True, exist_ok=True)
            command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
                       "-filter_complex", ";".join(graph), "-loop", "0", str(OUT)]  # fmt: skip
            done = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603, S607
            if done.returncode != 0:
                raise SystemExit("ffmpeg failed:\n" + done.stderr)
    finally:
        server.shutdown()
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
