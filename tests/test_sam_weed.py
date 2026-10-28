import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sam_weed_test", ROOT / "evals" / "sam_weed_test.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def box(h, w, y0, y1, x0, x1):
    m = np.zeros((h, w), dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


def test_iou():
    a, b = box(10, 10, 0, 5, 0, 10), box(10, 10, 0, 10, 0, 10)
    assert ev.iou(a, b) == 0.5 and ev.iou(np.zeros((4, 4), bool), np.zeros((4, 4), bool)) == 1.0


def test_cell_scores_spray_only_cells_with_predicted_cover():
    truth = box(64, 64, 0, 8, 0, 8)  # one weed in the top-left 32 px cell
    pred = box(64, 64, 2, 4, 2, 4)  # SAM saw part of it
    hit, weed, sprayed, total = ev.cell_scores(pred, truth, cell=32, cover=0.001)
    assert (hit, weed, sprayed, total) == (64, 64, 32 * 32, 64 * 64)  # whole weed hit, 1 of 4 cells sprayed


def test_cover_threshold_skips_sparse_cells():
    truth = box(64, 64, 0, 8, 0, 8)
    pred = box(64, 64, 0, 1, 0, 1)  # 1 pixel = 0.1% of a 32 px cell
    assert ev.cell_scores(pred, truth, cell=32, cover=0.01)[2] == 0


def test_partial_edge_cells():
    truth = box(40, 40, 36, 40, 36, 40)  # weed in the bottom-right corner
    hit, weed, sprayed, total = ev.cell_scores(truth.copy(), truth, cell=32, cover=0.001)
    assert hit == weed == 16 and sprayed == 8 * 8 and total == 1600


@pytest.mark.parametrize("rows, expected", [
    ({32: (0.96, 0.40), 96: (0.99, 0.60)}, "PASS"),
    ({32: (0.90, 0.40), 96: (0.97, 0.45)}, "BORDERLINE"),
    ({32: (0.99, 0.70), 96: (0.99, 0.80)}, "FAIL"),
    ({32: (0.50, 0.10), 96: (0.80, 0.30)}, "FAIL"),
])
def test_verdict(rows, expected):
    assert ev.verdict(rows) == expected


def test_excess_green_picks_plants_not_soil():
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    img[0, 0] = (40, 160, 40)  # leaf
    img[0, 1] = (140, 110, 80)  # soil
    img[1, 0] = (200, 200, 200)  # grey stone
    assert ev.excess_green(img).tolist() == [[True, False], [False, False]]


def test_mask_from_sam_text_pastes_at_the_box():
    text = "<0f>0<|box;x1=10;y1=20;x2=14;y2=24;w=64;h=64|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>\n"
    m = ev.mask_from_sam_text(text, 64, 64)
    assert m.sum() == 10 and m[20:25, 10:15].sum() == 10  # all 10 mask pixels inside the box
