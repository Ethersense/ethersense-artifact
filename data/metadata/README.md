# Released recording metadata

`release_datasets.json` lists 95 valid WAV recordings and archive/member integrity checks;
`recordings.csv` provides a flat condition-label mapping. `auxiliary_captures.json` lists sixteen
signed-IQ captures without WAV headers. Per-cohort part indexes are in `parts/`; the earlier two
archive streams also use `review_parts.json`. These indexes permit reconstruction without LFS.

`figure_data_map.csv` maps the added measurement figures to actual released cohorts. The 59-unit
conductor-length CSV is transcribed from the latest manuscript table, retaining NR and N/A entries.
Source provenance describes the recorded-data code export and documented edits. Withdrawn or
invalid recordings are not packaged.
