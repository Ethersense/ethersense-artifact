# EtherSense supplementary measurement artifact

**Data and code are being uploaded progressively.** This release contains the valid supplementary recordings and numerical inputs associated with the added figures.

Anonymous review access: https://anonymous.4open.science/r/ethersense-artifact-236E/

## Download and validate

Download and extract the repository ZIP from the anonymous page, then run:

```sh
python scripts/assemble_data.py
python scripts/validate_data.py
python scripts/reproduce_all.py manifest
```

Python 3.10 or later is sufficient for inventory validation. Every released archive has ordinary binary parts of at most 6 MiB; Git LFS is not required for reconstruction from this snapshot. Archive and member names retain their original measurement provenance; the manifest adds explicit condition labels.

## Released measurements

| Dataset | Valid recordings |
|---|---:|
| `cord_length_20261101` | 4 WAVs |
| `wall_pairs_20261101` | 6 WAVs |
| `parallel_load_states` | 4 WAVs |
| `along_line_1to10m` | 10 WAVs |
| `wire_distance_across_line` | 9 WAVs |
| `daily_stability_12days` | 12 WAVs |
| `cord_routing_48` | 48 WAVs |
| `router_waveform_reference` | 2 WAVs |
| `router_ab_cs8` | 6 signed-IQ captures |
| `wifi_feature_probe_cs8` | 10 signed-IQ captures |

There are **95 valid WAV recordings and 16 signed-IQ captures** in these archives. Raw TCP measurements and associated acquisition records are in `data/figure_data/wifi_tcp/`. The [figure-data index](docs/figure_data_map.md) maps the added figures to recordings, numerical tables and compact arrays; the [recording manifest](data/metadata/recordings.csv) gives condition labels and hashes.

## Scope

The released groups include the 1–10 m receiver-position series, parallel-load states, 48 cord-routing records, twelve-day heater recordings, the new paired-wall study and the direct 1–4 m cord-length comparison. Receiver position, cord routing labels and physical cord length are distinct quantities.

Only author-approved valid cohorts are released. Old wall data, withdrawn 1587 MHz runs, invalid cable entries, withdrawn ON/OFF experiments and excluded later router campaigns are omitted. Original-paper plotting notebooks and simulated-data figure code are not distributed. The complete original recognition dataset is outside this supplementary release.

## Analysis and citation

Historical numerical sources are retained under `revision_workspace/`; additional recorded-data analyses are in `analysis/`. See [analysis entry points](docs/analysis_entry_points.md) and [envelope replay](docs/replay_envelope_analysis.md).

Anonymous. *EtherSense: Supplementary Measurement Data and Analysis Code*. 2026. https://anonymous.4open.science/r/ethersense-artifact-236E/
