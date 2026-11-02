# Anonymous EtherSense review artifact

This fixed review snapshot contains the released measurement and analysis code, four valid
1/2/3/4 m cable-length recordings and six recordings in three no-wall/with-wall pairs.
Only the new wall batch is included. See [release scope](RELEASE_SCOPE.md).

## Download and verify

Download the complete repository ZIP using the anonymous repository's download button and extract
it. Open a terminal in the extracted folder, then run:

```sh
python scripts/assemble_data.py
python scripts/validate_data.py
python scripts/reproduce_all.py manifest
```

Python 3.10 or later is sufficient for these commands; no additional packages or GitHub account
are needed. Each data part is at most 6 MiB and is stored directly in this review snapshot. Git LFS
is not needed. The first command checks every part and reconstructs the two original ZIP byte
streams. The remaining commands check archive hashes, the valid-record inventory and WAV headers.

## Released data

| Archive after assembly | Measurements | Record labels |
|---|---|---|
| `data/raw/cable_lengths/cable_lengths_1to4m.zip` | 1, 2, 3, 4 m; one recording per length | `cable_1m` through `cable_4m` |
| `data/raw/wall_pairs/wall_pairs.zip` | Three no-wall/with-wall pairs | `wall_pair_01_no_wall`, `wall_pair_01_with_wall`, etc. |

The [recording manifest](data/metadata/recordings.csv) maps these labels to the original WAV names.
Original WAV bytes and the two reconstructed ZIP hashes are preserved. Recording timestamps are
provenance labels and are not independently verified acquisition dates.

## Code and scope

Historical measurement and numerical-analysis sources are in `revision_workspace/`; preprocessing
helpers are in `src/`. Read [workspace instructions](revision_workspace/README.md) before using
historical scripts, whose original inputs and equipment may be required. Original-paper figure
generation and simulated-data plotting code are excluded. This release does not reproduce the
complete recognition evaluation. Invalid recordings, withdrawn wall studies and excluded router
campaigns are omitted.

This snapshot is fixed for review. Cite the anonymous page supplied with the submission. The
original public repository URL and author identities are intentionally omitted from this snapshot.
