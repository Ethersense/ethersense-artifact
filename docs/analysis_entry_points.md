# Numerical analysis entry points

The historical numerical sources remain under `revision_workspace/`. New cable-length and wall-pair
programs are under `analysis/cable_lengths/` and `analysis/wall_pairs/`; their `analyze.py` entry point
takes the released ZIP path as its first argument and writes spectra and numerical summaries beside
the code directory. The cable input contains exactly four valid WAVs; the wall input contains six.
The companion comparison/postprocessing stage reads that generated cache.

`analysis/propagation/deep_features.py` and `psd_structure.py` implement the recorded-data
modulation and comb descriptors. Original-paper plotting notebooks, simulated-data figure sources,
withdrawn 1587 MHz data, old wall cohorts, invalid cable entries and withdrawn ON/OFF tests are absent.
