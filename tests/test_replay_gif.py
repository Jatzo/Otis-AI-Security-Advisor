"""The scroll expression the replay GIF script hands to ffmpeg. The picture itself is checked by
looking at it, so this covers the one piece of arithmetic that can be wrong without any error."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_path = ROOT / "scripts" / "make_replay_gif.py"
_loaded = importlib.util.spec_from_file_location("make_replay_gif", _path)
make_replay_gif = importlib.util.module_from_spec(_loaded)
sys.modules["make_replay_gif"] = make_replay_gif
_loaded.loader.exec_module(make_replay_gif)

WAYPOINTS = ((0, 0), (1.6, 0), (2.6, 330), (5.6, 330), (6.8, 1000), (8.0, 1000))


def position(waypoints: tuple, seconds: float) -> float:
    """Evaluates the expression the way ffmpeg would, with its if and lt functions."""
    expression = make_replay_gif.scroll(waypoints).replace("if(", "choose(").replace("lt(", "less(")
    names = {
        "choose": lambda test, yes, no: yes if test else no,
        "less": lambda a, b: a < b,
        "t": seconds,
    }
    return eval(expression, names)  # noqa: S307 - an expression this test's own script built


def test_the_window_holds_at_each_waypoint_and_ends_where_the_last_one_says():
    expected = ((0, 0), (1.6, 0), (2.6, 330), (4.0, 330), (5.6, 330), (6.8, 1000), (8.0, 1000))
    for seconds, where in expected:
        assert abs(position(WAYPOINTS, seconds) - where) < 1e-6, seconds


def test_the_window_moves_down_smoothly_and_stays_between_the_two_ends_of_a_move():
    steps = [position(WAYPOINTS, 1.6 + i * 0.05) for i in range(21)]
    assert steps == sorted(steps)
    assert min(steps) >= 0 and max(steps) <= 330
    assert 0 < steps[10] < 330


def test_a_scene_with_one_hold_stays_where_it_starts():
    hold = ((0, 330), (4.0, 330))
    assert position(hold, 0) == position(hold, 2) == position(hold, 4) == 330
