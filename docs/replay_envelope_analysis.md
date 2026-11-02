# Replay the recorded envelope descriptors

After reconstructing and validating the archives, run from the repository root:

```sh
python analysis/propagation/deep_features.py --jobs analysis/propagation/released_jobs.json --out results/modulation --workers 4
```

This streams the released WAV recordings and computes the numerical envelope descriptors. It does
not run the original device classifier. The explicit jobs list uses the actual split archive paths,
preserves the recorded member names and excludes withdrawn cohorts. Full processing reads tens of
gigabytes after decompression; use a suitable compute machine. The figure-data CSVs and compact
arrays are provided separately in `data/figure_data/`.
