# EtherSense Artifact

Major-revision measurement code and recorded data for EtherSense.
Repository: https://github.com/Ethersense/ethersense-artifact

## This release

This batch contains the measurement and analysis sources from the major-revision campaigns through
**2026-10-22**, together with the **valid cable-length and new wall-pair recordings** confirmed by the
authors. Only confirmed-valid recordings are packaged: invalid entries were removed from the archives
before upload. The remaining campaign recordings and the recognition implementation are being
curated and will follow in subsequent uploads. Figure-generation utilities are maintained separately
and are not part of this release; the released analysis code and processed tables cover every
measured quantity reported in the paper.

| Path | Included content |
|---|---|---|
| `src/preprocessing/` | Router capture helpers, the PSD C source and the historical ARM PSD binary |
| `src/features/analyze_ab.py` | Historical recorded-data A/B PSD analysis |
| `revision_workspace/results/` | Measurement and analysis sources from the 2026-10-14 to 2026-10-22 campaigns |
| `data/raw/cord_length_20261101/cable_lengths_1to4m.zip` | Four WAVs: 1, 2, 3 and 4 m; valid WAV bytes preserved |
| `data/raw/wall_pairs_20261101/2026_11_02.zip` | Six WAVs forming three new no-wall / wall pairs |
| `data/metadata/` | Archive hashes, valid-record labels and source provenance |
| `data/processed/` | Measured summary tables for the two new valid batches |

## Download and validate

Python 3.10+ is sufficient for inventory validation (standard library only). Git LFS stores the ZIPs.

```sh
git clone https://github.com/Ethersense/ethersense-artifact.git
cd ethersense-artifact
git lfs install
git lfs pull
python scripts/validate_data.py
python scripts/reproduce_all.py manifest
```

Validation checks archive hashes and the stored ZIP inventory. Manifest inspection additionally
reads WAV headers. It does not recompute spectra, run recognition or decompress the full payload.
For the historical numerical sources, install `requirements.txt` and read
[`revision_workspace/README.md`](revision_workspace/README.md); each entry documents its expected
inputs and host-specific parameters.

## Labels and measurement scope

- Cable WAVs in timestamp order correspond to **1 m, 2 m, 3 m, 4 m**. Invalid or empty source entries
  were removed before packaging and are not present in the released ZIP.
- New wall WAVs in timestamp order form pairs **1/2**, **3/4**, **5/6**. Odd entries are no-wall;
  even entries are wall-present. The new batch is the sole wall dataset used for current analysis.
- All ten released WAV headers report two channels, **20 MS/s**, 8-bit PCM. Filename suffixes label
  tuning centers: 20 MHz for cable and 20.038 MHz for wall; the latter is not the sample rate.
- `2026_11_02` is the preserved source archive name, not independently verified acquisition dating.
- Acquisition conditions for the new batches are being compiled and will be added to
  `data/metadata/` as they are finalised. Spectrum similarity and visible peaks are not
  classification accuracy, calibrated dBm or wall insertion loss.

The original-paper recognition implementation is being prepared for upload. Directories for the
remaining experiments stay in place while their recordings are curated; [`RELEASE_SCOPE.md`](RELEASE_SCOPE.md)
records the current scope of this batch.

## Citation

This artifact is published anonymously. If you use the released recordings or the analysis code,
please cite the repository:

> Anonymous. *EtherSense Artifact: Released Recordings, Analysis Code and Revision Workspace*.
> GitHub, 2026. <https://github.com/Ethersense/ethersense-artifact>

```bibtex
@misc{ethersense_artifact_2026,
  author       = {Anonymous},
  title        = {{EtherSense} Artifact: Released Recordings, Analysis Code and Revision Workspace},
  year         = {2026},
  month        = nov,
  publisher    = {GitHub},
  howpublished = {\url{https://github.com/Ethersense/ethersense-artifact}},
  note         = {Anonymous research artifact accompanying the IMWUT submission
                  ``Lens-Free, Plug-Free, and Retrofit-Free: Repurposing Wi-Fi APs
                  into Ubiquitous Electrical Sentinels''}
}
```

The machine-readable form is [`CITATION.cff`](CITATION.cff).
