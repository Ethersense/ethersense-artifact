# Major-revision code through 2026-10-22

The historical source layout is retained as `results/<campaign>/code/` so relative imports keep
working.

| Campaign | Sources |
|---|---|
| 2026-10-14 supplementary paths/parallel loads | `results/ethersense_supplemental/code/` |
| 2026-10-16 cord routing / RF64 / Welch | `results/ethersense_k4_20261016/code/` |
| 2026-10-20 generic modulation worker | `results/ethersense_deep_20261020/code/deep_features.py` |
| 2026-10-20 Wi-Fi/PSD and protected trials | `results/ethersense_bench_20261020/code/` |
| 2026-10-21 twelve-date stability | `results/ethersense_stability_20261021/code/` |
| 2026-10-21 Wi-Fi/spectral retention | `results/ethersense_wifi_detection_20261021/code/` |
| 2026-10-22 prototype preflight | `results/ethersense_fullstack_20261022/code/` |

Capture/PSD sources and the historical ARM binary live in `../src/preprocessing/`, and the A/B
analysis program in `../src/features/analyze_ab.py`. The earlier wall-study sources and results are
being curated and will be uploaded with the remaining batches.

These are the historical source files, kept with their original layout. The earlier inventories,
archives and cached spectra are being assembled for upload, and each entry documents its expected
inputs and host-specific parameters; no generated observations stand in for missing inputs. Heavy
raw-data transforms run on a suitable compute host, and this batch performed no new capture or
spectrum recomputation. The original-paper plotting notebooks and the standalone synthetic
demonstrations are being prepared for upload in the same way. Shared style helpers retain
measured-data plotting with deterministic point offsets. See
`../data/metadata/source_provenance.json` for the copied-source hashes and documented edits.
