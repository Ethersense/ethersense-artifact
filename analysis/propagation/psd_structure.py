"""Cross-dataset spectral-structure features from the cached Welch spectra (65536 bins, 305.2 Hz).

For each record: full-band power; 1 MHz band profile; smooth envelope (running median over ~0.6 MHz);
narrow-line contrast (log-PSD minus 201-bin running median); harmonic-comb periodicity of the contrast
(autocorrelation over 3-600 kHz lags, reported as the strongest lag and its normalised height);
excess envelope over the matched background of the same session.
Writes analysis/psd_structure.csv, band_profiles.csv, envelope_excess.npz.
"""
import csv, io, json
from pathlib import Path
import numpy as np
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'ethersense_deep_20261020' / 'analysis'; OUT.mkdir(parents=True, exist_ok=True)
SRC = {'S': ROOT / 'ethersense_supplemental' / 'output', 'K': ROOT / 'ethersense_k4_20261016' / 'output', 'W': ROOT / 'ethersense_wall_20261018' / 'output'}
BG = {'S_A': 'S_A09', 'S_B': 'S_A09', 'S_C': 'S_C04', 'W': 'W_BG'}


def db(x): return 10 * np.log10(np.maximum(x, 1e-30))


def load(tag, rid):
    z = np.load(SRC[tag] / (rid + '_spectra.npz'))
    p = z['mean_psd'].astype(float)
    if 'time_psd' in z and tag == 'W':           # wall batch: time-median (robust to output collapses)
        p = np.median(z['time_psd'].astype(float), axis=0)
    return z['offset_hz'].astype(float), p


def comb(c, df):
    x = np.clip(c, 0, None); x = x - x.mean()
    ac = np.fft.irfft(np.abs(np.fft.rfft(x, 2 * len(x))) ** 2)[:len(x)]; ac /= ac[0]
    lo, hi = int(3e3 / df), int(600e3 / df)
    i = lo + int(np.argmax(ac[lo:hi]))
    return i * df, float(ac[i])


def main():
    jobs = json.loads((ROOT / 'ethersense_deep_20261020' / 'code' / 'jobs.json').read_text(encoding='utf-8'))
    rows, prof, env = [], [], {}
    for j in jobs:
        rid = j['record_id']; tag = rid[0]
        if tag == 'R': continue                      # reference ZIP has no cached Welch spectrum; handled from deep features
        f, p = load(tag, rid[2:]); df = f[1] - f[0]
        d = db(p); c = d - median_filter(d, 201, mode='nearest'); c[np.abs(f) < 5e3] = 0
        e = median_filter(d, 2001, mode='nearest'); env[rid] = e[::64].astype(np.float32)
        lag, h = comb(c, df)
        pk = np.where((c[1:-1] > c[:-2]) & (c[1:-1] >= c[2:]) & (c[1:-1] >= 6))[0] + 1
        rows.append(dict(record_id=rid, dataset=j['dataset'], power_db=float(db(p.sum() * df)), floor_median_db=float(np.median(d)),
                         n_lines_6db=int(len(pk)), comb_lag_khz=round(lag / 1e3, 2), comb_strength=round(h, 4),
                         env_ptp_db=float(np.ptp(e[np.abs(f) < 9.5e6]))))
        for b in range(-10, 10):
            m = (f >= b * 1e6) & (f < (b + 1) * 1e6) & (np.abs(f) > 5e3)
            prof.append(dict(record_id=rid, band_offset_mhz=b, power_db=float(db(p[m].sum() * df))))
    for name, data in (('psd_structure.csv', rows), ('band_profiles.csv', prof)):
        with io.open(OUT / name, 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
    np.savez_compressed(OUT / 'envelopes.npz', offset_hz=f[::64], **env)
    print('records', len(rows))


if __name__ == '__main__':
    main()
