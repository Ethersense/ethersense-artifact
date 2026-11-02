"""Raw-I/Q deep features for every EtherSense recording (runs on the Zhiyuan CPU node).

Per record (streamed straight from the ZIP, nothing extracted):
  * STFT: Hann, N=1024, no overlap (frame rate fs/1024 = 19531.25 Hz); bin powers summed into 128 subbands of 8 bins
    (156.25 kHz each) -> subband power time series P[t, s].
  * Mains-synchronous amplitude modulation: for every subband, rFFT of P[:, s] (mean removed);
    modulation index spectrum M(f) = 2|FFT| / (n * mean). The 100 Hz line (rectifier ripple of 50 Hz mains) is located
    on the full-band series inside 99.0-101.0 Hz; harmonics k*f100/2 (k=1..12) are read per subband as the maximum
    within +-0.35 Hz, the noise floor as the median of M over 20-600 Hz excluding +-1.5 Hz around every 25 Hz multiple.
  * Impulsiveness of the full-band frame power: kurtosis, p99.9/median, fraction of frames > 10 x median.
  * Full-band modulation spectrum 0-1500 Hz and the full-band power decimated to 1220.7 Hz are stored for plotting.
Digital units only. I/Q convention ch1 + j ch2 (unconfirmed for WAV recordings).
"""
import argparse, concurrent.futures, json, struct, time, zipfile, zlib
from pathlib import Path
import numpy as np

NFFT = 1024; GROUP = 8; NSUB = NFFT // GROUP; CHUNK_FRAMES = 2048
HARM = list(range(1, 13))           # multiples of mains/2 ... k * 50 Hz nominal


def header(zf, info):
    with zf.open(info) as fh:
        h = fh.read(4096)
    pos = 12; ds64 = None; fmt = None
    while pos + 8 <= len(h):
        cid = h[pos:pos + 4]; sz = struct.unpack('<I', h[pos + 4:pos + 8])[0]
        if cid == b'ds64': ds64 = struct.unpack('<QQQ', h[pos + 8:pos + 32])
        if cid == b'fmt ': fmt = struct.unpack('<HHIIHH', h[pos + 8:pos + 24])
        if cid == b'data':
            dl = ds64[1] if (sz == 0xFFFFFFFF and ds64) else sz
            return dict(offset=pos + 8, data_bytes=dl, fs=fmt[2], ch=fmt[1], bits=fmt[5], align=fmt[4])
        pos += 8 + sz + (sz & 1)
    raise ValueError('no data chunk')


def one(job):
    t0 = time.time()
    zf = zipfile.ZipFile(job['archive']); info = zf.getinfo(job['member']); hd = header(zf, info)
    fs = hd['fs']; u8 = hd['bits'] == 8
    assert hd['ch'] == 2 and hd['bits'] in (8, 16)
    win = np.hanning(NFFT + 1)[:-1].astype(np.float32)
    nframes = hd['data_bytes'] // hd['align'] // NFFT
    P = np.empty((nframes, NSUB), np.float32)
    crc = 0; done = 0; fb = NFFT * hd['align']
    with zf.open(info) as fh:
        crc = zlib.crc32(fh.read(hd['offset']), crc)
        rem = hd['data_bytes']
        while rem:
            raw = fh.read(min(rem, CHUNK_FRAMES * fb)); rem -= len(raw); crc = zlib.crc32(raw, crc)
            k = min(len(raw) // fb, nframes - done)
            if k <= 0: continue
            a = np.frombuffer(raw[:k * fb], np.uint8 if u8 else '<i2').reshape(k, NFFT, 2).astype(np.float32)
            a = (a - 128) / 128 if u8 else a / 32768
            x = (a[..., 0] + 1j * a[..., 1]).astype(np.complex64)
            x -= x.mean(axis=1, keepdims=True)
            p = np.abs(np.fft.fftshift(np.fft.fft(x * win, axis=1), axes=1)) ** 2
            P[done:done + k] = p.reshape(k, NSUB, GROUP).sum(axis=2)
            done += k
        crc = zlib.crc32(fh.read(), crc)
    crc_ok = (crc & 0xffffffff) == info.CRC
    P = P[:done]; n = len(P); fr = fs / NFFT
    full = P.sum(axis=1) - P[:, NSUB // 2]            # exclude the DC subband
    fm = np.fft.rfftfreq(n, 1 / fr)
    def modspec(series):
        m = series.mean(); X = np.fft.rfft(series - m)
        return 2 * np.abs(X) / (n * m)
    Mf = modspec(full)
    # timeline scale is not assumed exact (PC recorders may drop samples): pick the 100 Hz candidate in 97-105 Hz that
    # maximises the summed modulation index at k*f/2, k=1..6 (each read as the max within +-0.35 Hz)
    best = (-1, 100.0)
    for c in fm[(fm >= 97.0) & (fm <= 105.0)]:
        sc = sum(Mf[np.abs(fm - k * c / 2) <= 0.35].max() for k in range(1, 7))
        if sc > best[0]: best = (sc, float(c))
    f100 = best[1]
    base = f100 / 2
    excl = np.zeros(len(fm), bool)
    for q in range(1, 25): excl |= np.abs(fm - 25 * q) < 1.5
    floor_band = (fm >= 20) & (fm <= 600) & ~excl
    def harmonics(M):
        out = []
        for k in HARM:
            w = np.abs(fm - k * base) <= 0.35
            out.append(float(M[w].max()) if w.any() else np.nan)
        return out
    full_h = harmonics(Mf); full_floor = float(np.median(Mf[floor_band]))
    sub_h = np.zeros((NSUB, len(HARM)), np.float32); sub_floor = np.zeros(NSUB, np.float32); sub_mean = P.mean(axis=0)
    for s in range(NSUB):
        M = modspec(P[:, s].astype(np.float64)); sub_h[s] = harmonics(M); sub_floor[s] = np.median(M[floor_band])
    q = np.percentile(full, [50, 99.9])
    z = (full - full.mean()) / full.std()
    keep = fm <= 1500
    lowk = fm <= 420
    sub_mod = np.stack([modspec(P[:, s].astype(np.float64))[lowk] for s in range(NSUB)]).astype(np.float16)
    dec = 16; nd = n // dec
    np.savez_compressed(Path(job['out']) / (job['record_id'] + '_deep.npz'),
                        mod_freq=fm[keep].astype(np.float32), mod_full=Mf[keep].astype(np.float32),
                        full_dec=full[:nd * dec].reshape(nd, dec).mean(1).astype(np.float32),
                        sub_harm=sub_h, sub_floor=sub_floor, sub_mod=sub_mod, sub_mod_freq=fm[lowk].astype(np.float32), sub_mean=sub_mean.astype(np.float32),
                        sub_offset_hz=((np.arange(NSUB) - NSUB // 2) * GROUP * fs / NFFT + (GROUP / 2 - 0.5) * fs / NFFT).astype(np.float32))
    meta = dict(record_id=job['record_id'], dataset=job['dataset'], member=job['member'], crc_ok=bool(crc_ok), fs=fs, bits=hd['bits'],
                frames=n, seconds=n / fr, frame_rate=fr, mod_resolution_hz=fr / n, f100_hz=f100, mains_hz=base,
                full_harm=full_h, full_floor=full_floor, full_100_snr=full_h[1] / full_floor,
                kurtosis=float((z ** 4).mean()), p999_over_median=float(q[1] / q[0]),
                frac_gt10x_median=float((full > 10 * q[0]).mean()), wall_s=time.time() - t0)
    (Path(job['out']) / (job['record_id'] + '_deep.json')).write_text(json.dumps(meta), encoding='utf-8')
    return meta


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--jobs', required=True); ap.add_argument('--out', required=True); ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args(); Path(a.out).mkdir(parents=True, exist_ok=True)
    jobs = json.loads(Path(a.jobs).read_text(encoding='utf-8'))
    todo = [dict(j, out=a.out) for j in jobs if not (Path(a.out) / (j['record_id'] + '_deep.json')).exists()]
    print('START', len(jobs), 'pending', len(todo), flush=True); t = time.time()
    with concurrent.futures.ProcessPoolExecutor(a.workers) as ex:
        for f in concurrent.futures.as_completed([ex.submit(one, j) for j in todo]):
            m = f.result()
            print('DONE', m['record_id'], 'crc', m['crc_ok'], 'f100 %.3f' % m['f100_hz'], 'snr100 %.1f' % m['full_100_snr'], '%.1fs' % m['wall_s'], flush=True)
    print('COMPLETE %.1f s' % (time.time() - t), flush=True)


if __name__ == '__main__':
    main()
