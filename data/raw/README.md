# Released measurement archives

Run `python scripts/assemble_data.py` from the repository root to reconstruct the archives from
`data/parts/`. Then run `python scripts/validate_data.py` and
`python scripts/reproduce_all.py manifest`.

- `cable_lengths/cable_lengths_1to4m.zip`: four valid recordings in 1/2/3/4 m order.
- `wall_pairs/wall_pairs.zip`: three no-wall/with-wall pairs; only the new wall batch is included.

Review labels map to the preserved original WAV names in `../metadata/recordings.csv`. The
reconstructed archives match the released SHA-256 hashes. Invalid or withdrawn recordings are
not included. Earlier wall datasets remain withdrawn and are not scheduled for upload.
