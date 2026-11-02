# Acquisition and PSD sources

Included here: `es_common.ps1`, `capture_group.ps1`, `capture_one.sh`, `deploy_and_test.ps1`,
`diag.sh`, `online_bench.sh`, `es_psd.c`, and the historical ARM ELF `es_psd` (67,912 bytes). The C
implementation performs a Hann-windowed FFT and reports digital full-band and subband power; it is the
PSD front end that feeds the later stages.

The historical host scripts use `%USERPROFILE%/Desktop/EtherSense` and a separately provisioned SSH
key at `%USERPROFILE%/.ssh/ethersense_mt3000`. No key is distributed, so supply and verify your own
router connection and hardware configuration. `deploy_and_test.ps1` additionally expects HackRF
command-line tools in the host `bin/` directory; install those third-party binaries for your own
platform.

Build the PSD program with a Linux/ARM toolchain suitable for your target, for example:

```sh
cc -O3 -o es_psd es_psd.c -lm
```

Building for the router from another architecture requires an ARM cross compiler. The bundled binary
is a byte-for-byte copy of the historical build; rebuilding it and re-running hardware trials are part
of the remaining work.
