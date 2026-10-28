# Leafy spurge per survey plot: frozen Meta backbones + logistic probe

Leafy Spurge Dataset (MPG Ranch, western Montana; CC BY 4.0, doi:10.57967/hf/2508): 1.27 cm drone orthomosaic,
900 GNSS survey plots (0.5 m, spurge present or absent; 457 present) in 9 spatial clusters.
Run: `uv run --with modal python train/spurge_modal.py` (L4).

Each plot's 1024 px context image is embedded with a frozen backbone. Patch features are averaged over a window
centred on the plot, then a standardised logistic regression (C = 0.1) is fitted. "full" uses the 13 m image as is;
"zoom" takes the centre 3.25 m and upscales it 4x first.
- Official test: train on the official train split, test on its test split (one whole cluster). The dataset
  paper's best baseline is 0.85.
- Leave one cluster out (LOCO): each of the 9 clusters is tested by a probe trained on the other 8. The
  threshold is set from out-of-fold probabilities on the training clusters only, to catch 95% of spurge plots.
  Recall and "absent flagged" pool all 9 test clusters.

| backbone | view | window (m) | official test acc | LOCO acc | LOCO AUC | recall | absent plots flagged |
|---|---|---|---|---|---|---|---|
| dinov2-base | full | 0.4 | 85.0% | 79.2% | 0.88 | 93.4% | 66.6% |
| dinov2-base | zoom | 0.4 | 82.0% | 80.0% | 0.87 | 95.0% | 64.3% |
| dinov2-base | full | 0.8 | 82.0% | 78.1% | 0.86 | 95.4% | 68.4% |
| dinov2-large | full | 0.4 | 75.0% | 76.5% | 0.85 | 94.3% | 67.9% |
| dinov2-large | zoom | 0.4 | 78.0% | 77.1% | 0.85 | 94.7% | 61.2% |
| dinov2-large | full | 0.8 | 80.0% | 76.9% | 0.85 | 94.1% | 70.0% |
| dinov2-base | zoom | 0.8 | 78.0% | 76.0% | 0.84 | 95.6% | 67.3% |
| dinov3-vits16-pretrain-lvd1689m | zoom | 0.4 | 81.0% | 77.1% | 0.84 | 95.0% | 71.6% |
| dinov2-large | zoom | 0.8 | 80.0% | 76.3% | 0.84 | 95.0% | 72.9% |
| dinov3-vits16-pretrain-lvd1689m | zoom | 0.8 | 81.0% | 75.3% | 0.84 | 95.0% | 71.8% |
| dinov3-vits16-pretrain-lvd1689m | full | 0.4 | 64.0% | 73.3% | 0.83 | 94.1% | 71.8% |
| dinov2-large | full | 1.6 | 78.0% | 71.9% | 0.82 | 95.4% | 70.0% |
| dinov3-vits16-pretrain-lvd1689m | zoom | 1.6 | 81.0% | 73.7% | 0.82 | 94.5% | 79.7% |
| dinov2-base | zoom | 1.6 | 80.0% | 72.9% | 0.80 | 95.8% | 74.7% |
| dinov3-vits16-pretrain-lvd1689m | zoom | 3.25 | 80.0% | 72.6% | 0.80 | 95.0% | 80.1% |
| dinov2-base | full | 1.6 | 71.0% | 73.1% | 0.80 | 94.1% | 77.7% |
| dinov3-vits16-pretrain-lvd1689m | full | 0.8 | 64.0% | 71.8% | 0.79 | 95.4% | 77.0% |
| dinov2-large | zoom | 1.6 | 75.0% | 70.2% | 0.78 | 95.4% | 83.7% |
| dinov2-base | zoom | 3.25 | 74.0% | 67.6% | 0.78 | 95.0% | 76.5% |
| dinov2-large | full | 3.2 | 72.0% | 66.4% | 0.75 | 95.2% | 84.0% |
| dinov2-large | zoom | 3.25 | 75.0% | 68.4% | 0.75 | 94.7% | 83.1% |
| dinov3-vits16-pretrain-lvd1689m | full | 1.6 | 60.0% | 65.3% | 0.74 | 95.0% | 81.5% |
| dinov2-base | full | 3.2 | 69.0% | 67.5% | 0.74 | 95.0% | 85.1% |
| dinov3-vits16-pretrain-lvd1689m | full | 3.2 | 56.0% | 64.0% | 0.72 | 94.3% | 84.0% |
| dinov3-vits16-pretrain-lvd1689m | full | 13.0 | 57.0% | 56.7% | 0.66 | 95.2% | 91.2% |
| dinov2-large | full | 13.0 | 59.0% | 58.8% | 0.63 | 94.3% | 89.6% |
| dinov2-base | full | 13.0 | 59.0% | 59.3% | 0.63 | 94.3% | 93.5% |

The best probe (DINOv2-B, 0.4 m) matches the paper's 0.85 but does not beat it. Small windows win: the plot's
own 0.4 m beats every wider context, and the whole 13 m image is near chance. At 95% recall about two-thirds
of the absent plots are also flagged. The plots were sampled around spurge, so the share of a whole field that
would be sprayed has to be measured on a map, not read off this table.

## Fine-tuning DINOv2-B (2026-10-28)

`uv run --with modal python train/spurge_finetune_modal.py`: the last 2 of 12 blocks and a linear head on the
plot's centre 2 x 2 patch tokens (0.36 m), trained on the centre 448 px (5.7 m) of each plot for 8 epochs with flips
and quarter turns (AdamW, 2e-5 for the blocks, 1e-3 for the head). Same tests as above.

| model | official test acc | official test AUC | LOCO acc | LOCO AUC |
|---|---|---|---|---|
| frozen DINOv2-B probe, 0.4 m (best above) | 85.0% | n/a | 79.2% | 0.88 |
| **DINOv2-B, last 2 blocks fine-tuned** | 83.0% | **0.971** | **86.7%** | **0.946** |

LOCO AUC by held-out cluster: 0.86, 0.91, 0.95, 0.96, 1.00, 0.95, 0.94, 0.98, 0.97. Accuracy is at a 0.5 cutoff; the
map picks its own cutoff for a catch rate, so the ranking (AUC) is what decides how much clean ground it sprays.

## The Montana map with the fine-tuned model (2026-10-28)

`train/spurge_finetune_modal.py` `map_block`: trained on the 5 clusters outside the demo block; catch-rate thresholds
from leave-one-cluster-out predictions within them; checked on the 4 clusters inside the block. Same block, same
1 m cells and >= 1% cover rule as the probe map.

| catch target | probe: held-out found / clean flagged / block sprayed | fine-tuned: found / clean flagged / block sprayed |
|---|---|---|
| 95% | 95.1% / 74.5% / 95% | 98.0% / 64.8% / 97% |
| 90% | 87.3% / 41.3% / 79% | 93.7% / 20.9% / 68% |
| **85% (the demo)** | 81.0% / 32.7% / 68% | **89.8% / 9.7% / 40%** |
| 80% | 76.1% / 24.0% / 54% | 85.9% / 8.2% / 27% |
| 70% | 68.8% / 16.3% / 35% | 78.5% / 5.1% / 14% |
| 60% | 61.5% / 7.7% / 17% | 72.7% / 3.1% / 7% |
