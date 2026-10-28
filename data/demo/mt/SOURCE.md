# Montana demo block: sources

- Drone orthomosaic tiles (rows 10-15, columns 6-11) and the 1000 survey plots: Leafy Spurge Dataset,
  MPG Ranch, western Montana, flown 2023-06-12. Doherty, Gurinas, Samsoe, Casper, Larkin, Ramsey, Trabucco and
  Salakhutdinov. CC BY 4.0, doi:10.57967/hf/2508, https://huggingface.co/datasets/mpg-ranch/leafy_spurge.
  `block.jpg`, `block.webp` and `prob.tif` are derived from it (downsampled imagery; ClearSwath's spurge probability).
- `water.geojson`: USGS National Hydrography Dataset (public domain), fetched 2026-10-28.
- Label: Tordon 22K, EPA Reg. No. 62719-6, EPA-accepted label of 2019-09-20 (`data/labels/tordon_22k.pdf`).

Rebuild with `scripts/build_demo_mt.py` (see its docstring).
