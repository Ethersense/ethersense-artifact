"""Independent offline PSD of an AP capture (numpy) vs the on-AP es_psd report for the same file.

Usage: python -I offline_check.py <cap.cs8> <psd.txt from es_psd>
Same definition as es_psd: int8 I/Q / 128, per-block mean removal, Hann N=4096, no overlap, averaged |X|^2,
scale 1/(fs*sum w^2); full band and 20 x 1 MHz bands (excluding |f| <= 5 kHz).
"""
import sys
import numpy as np

N, FS = 4096, 20e6
raw = np.fromfile(sys.argv[1], dtype=np.int8)
codes_i, codes_q = np.unique(raw[0::2]).size, np.unique(raw[1::2]).size
x = (raw[0::2].astype(np.float64) + 1j * raw[1::2]) / 128
nb = int(FS) // N  # es_psd reports after floor(1.0 s * fs / N) blocks
x = x[:nb * N].reshape(nb, N); x -= x.mean(axis=1, keepdims=True)
w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / N)
p = np.mean(np.abs(np.fft.fft(x * w, axis=1)) ** 2, axis=0) / (FS * np.sum(w ** 2))
p = np.fft.fftshift(p); f = (np.arange(N) - N // 2) * FS / N; df = FS / N
tot = 10 * np.log10(p.sum() * df)
band = [10 * np.log10(p[(f >= -10e6 + b * 1e6) & (f < -9e6 + b * 1e6) & (np.abs(f) > 5000)].sum() * df) for b in range(20)]
ap = [float(v) for v in [l for l in open(sys.argv[2]) if not l.startswith('#')][0].split()]
ap_tot, ap_band = ap[4], ap[5:25]
d = np.array(band) - np.array(ap_band)
print(f'blocks={nb} codes_used I={codes_i} Q={codes_q} clip_frac={np.mean(np.abs(raw) >= 127):.2e}')
print(f'full band: offline {tot:.3f}  AP {ap_tot:.2f}  diff {tot - ap_tot:+.3f} dB')
print(f'1 MHz bands: max |offline - AP| = {np.abs(d).max():.3f} dB (AP prints 2 decimals)')
