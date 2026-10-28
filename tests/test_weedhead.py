import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("weedhead", Path(__file__).resolve().parent.parent / "train" / "weedhead.py")
wh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wh)  # torch is only imported inside the GPU functions


def pair(weed_box, prob_box, value=0.9, size=100):
    w = np.zeros((size, size), bool)
    w[weed_box] = True
    p = np.zeros((size, size), np.float32)
    p[prob_box] = value
    return p, w


def test_coverage_sprays_whole_cells():
    p, w = pair(np.s_[0:10, 0:10], np.s_[2:4, 2:4])
    hit, sprayed = wh.coverage([(p, w)], threshold=0.5, cell=50)
    assert hit == 1.0 and sprayed == pytest.approx(0.25)  # one 50 px cell of four


def test_coverage_misses_below_threshold():
    p, w = pair(np.s_[0:10, 0:10], np.s_[0:10, 0:10], value=0.3)
    assert wh.coverage([(p, w)], threshold=0.5, cell=50) == (0.0, 0.0)


def test_cover_skips_sparse_cells_and_counts_partial_edges():
    p, w = pair(np.s_[0:10, 0:10], np.s_[2:4, 2:4])  # 4 px = 0.16% of a 50 px cell
    assert wh.coverage([(p, w)], threshold=0.5, cell=50, cover=0.01) == (0.0, 0.0)
    p, w = pair(np.s_[96:100, 96:100], np.s_[96:100, 96:100])  # 16 px = 1% of the 40 x 40 edge cell
    assert wh.coverage([(p, w)], threshold=0.5, cell=60, cover=0.01) == (1.0, pytest.approx(0.16))


def test_pick_threshold_is_the_highest_that_reaches_the_target():
    p, w = pair(np.s_[0:10, 0:10], np.s_[0:10, 0:10], value=0.4)
    assert wh.pick_threshold([(p, w)], target=0.95, cell=10) == pytest.approx(0.4, abs=0.011)


def test_pick_threshold_floor_when_unreachable():
    p, w = pair(np.s_[0:10, 0:10], np.s_[50:60, 50:60])  # predicts the wrong place
    assert wh.pick_threshold([(p, w)], target=0.95, cell=10) == 0.02
