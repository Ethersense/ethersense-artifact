# Release metadata

`release_datasets.json` and `recordings.csv` list the ten valid released WAVs, including archive
SHA-256, ZIP entry CRC and size, WAV header facts and author-confirmed labels. The four cable WAVs
also carry per-WAV SHA-256 from the streaming subset copy.

Invalid entries are omitted from the release archives by design, so no invalid-data cohort is
published. `source_provenance.json` records original-source and released-file hashes together with
the documented edits, and `code_exclusions.json` lists the host wrappers omitted from the source
export.

Metadata for the remaining recordings is being compiled and will be added here as those batches are
uploaded. The archive validator reads hashes and directory metadata; it does not recompute
full-payload CRCs.
