# Valid released data

| Archive | Released WAVs | Confirmed labels |
|---|---:|---|
| `cord_length_20261101/cable_lengths_1to4m.zip` | 4 | 1, 2, 3, 4 m in timestamp order |
| `wall_pairs_20261101/2026_11_02.zip` | 6 | Pairs 1/2, 3/4, 5/6; odd no-wall, even wall-present |

The cable archive is repacked from the original upload and keeps only the valid entries; the
individual valid WAV bytes are unchanged, with WAV SHA-256 and ZIP CRC values in
`../metadata/release_datasets.json`. The new wall archive is unchanged. Earlier wall recordings and their derived results remain withdrawn. Rejected or invalid
recordings and excluded router campaigns are not scheduled for upload.

Run `git lfs pull`, then `python scripts/validate_data.py` from the repository root.

Both datasets have WAV-header sample rate 20 MS/s, two channels and unsigned 8-bit PCM storage.
Filename center-frequency labels and the acquisition conditions are documented in the root README
and in `../metadata/`.
