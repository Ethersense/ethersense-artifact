"""EtherSense GL-MT3000 A/B analysis (runs on the Windows PC; numpy required, matplotlib optional).

Inputs : data/20261019_ab/{env,target}{1,2,3}.cs8 (hackrf_transfer: interleaved signed int8 I,Q; RF = fc + offset)
         openwrt示例.zip: 环境.wav / 目标.wav (RF64 PCM8 unsigned, 2 ch; ch1 = I, ch2 = Q assumed)
Method : Welch (Hann, 65536, 50 % overlap, per-segment mean removal), digital units x/128, no dBm calibration.
Output : analysis_20261019/{summary.json, metrics.csv, bands.csv, peaks.csv, diff_cells.csv, psd_reduced.csv, *.png, *.pdf}
"""
import csv, io, json, os, struct, sys, zipfile
import numpy as np

FS = 20e6; FC = 20e6; N = 65536; HOP = N // 2; CHUNK = 1 << 22
BASE = os.path.join(os.path.expanduser('~'), 'Desktop', 'EtherSense')
DATA = os.path.join(BASE, 'data', '20261019_ab')
REF_CANDIDATES = [os.path.join(BASE, 'reference', 'openwrt示例.zip'),
                  os.path.join(os.path.expanduser('~'), 'Desktop', 'ubicomp', '新建文件夹', 'IQ', 'openwrt示例.zip')]
REF = next((p for p in REF_CANDIDATES if os.path.exists(p)), REF_CANDIDATES[0])
REF_CRC = {'环境': 0x19C27A0E, '目标': 0xAEA827F0}   # CRC32 of the uploaded reference members
OUT = os.path.join(BASE, 'analysis_20261019')
WIN = np.hanning(N + 1)[:-1].astype(np.float32)          # periodic Hann
SCALE = 1.0 / (FS * float(np.sum(WIN.astype(np.float64) ** 2)))
f = np.fft.fftshift(np.fft.fftfreq(N, 1 / FS))
df = FS / N


def db(x): return 10 * np.log10(np.maximum(x, 1e-30))


def welch_stream(chunks):
    """chunks yields complex64 arrays; returns mean PSD (fftshifted), segment count, sample count, per-segment power."""
    acc = np.zeros(N); nseg = 0; carry = np.zeros(0, np.complex64); ns = 0; seg_pow = []
    for x in chunks:
        ns += len(x); buf = np.concatenate([carry, x]) if carry.size else x
        k = (len(buf) - N) // HOP + 1 if len(buf) >= N else 0
        for i in range(0, k, 16):
            m = min(16, k - i)
            fr = np.lib.stride_tricks.as_strided(buf[i * HOP:], (m, N), (buf.strides[0] * HOP, buf.strides[0])).copy()
            fr -= fr.mean(axis=1, keepdims=True); fr *= WIN
            p = np.abs(np.fft.fft(fr, axis=1)) ** 2 * SCALE
            acc += p.sum(0); seg_pow += list(p.sum(1) * df); nseg += m
        carry = buf[k * HOP:].copy() if k else buf.copy()
    return np.fft.fftshift(acc / nseg), nseg, ns, np.array(seg_pow)


def cs8_chunks(path, hist):
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(CHUNK * 2)
            if not b: break
            a = np.frombuffer(b, np.int8); hist += np.bincount((a.astype(np.int16) + 128), minlength=256)
            a = a.reshape(-1, 2).astype(np.float32) / 128
            yield (a[:, 0] + 1j * a[:, 1]).astype(np.complex64)


def wav_chunks(zf, member, hist):
    with zf.open(member) as fh:
        h = fh.read(4096); pos = 12; ds64 = None
        while True:
            cid = h[pos:pos + 4]; sz = struct.unpack('<I', h[pos + 4:pos + 8])[0]
            if cid == b'ds64': ds64 = struct.unpack('<QQQ', h[pos + 8:pos + 32])
            if cid == b'fmt ': fmt = struct.unpack('<HHIIHH', h[pos + 8:pos + 24])
            if cid == b'data': off = pos + 8; break
            pos += 8 + sz + (sz & 1)
        assert fmt[1] == 2 and fmt[5] == 8 and fmt[2] == FS, fmt
    rem = ds64[1] if sz == 0xFFFFFFFF else sz
    with zf.open(member) as fh:
        fh.read(off)
        while rem:
            b = fh.read(min(rem, CHUNK * 2)); rem -= len(b)
            a = np.frombuffer(b, np.uint8); hist += np.bincount(a, minlength=256)
            a = (a.reshape(-1, 2).astype(np.float32) - 128) / 128
            yield (a[:, 0] + 1j * a[:, 1]).astype(np.complex64)


def local_contrast(d, w=201):
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.pad(d, w // 2, mode='edge')
    return d - np.median(sliding_window_view(pad, w), axis=1)


def peaks(c, d, k=20):
    i = np.where((c[1:-1] > c[:-2]) & (c[1:-1] >= c[2:]) & (c[1:-1] >= 6))[0] + 1
    i = i[(np.abs(f[i]) > 5000) & (np.abs(f[i]) < 9.9e6)]
    sel = []
    for j in i[np.argsort(-c[i])]:
        if all(abs(f[j] - f[s]) > 20e3 for s in sel): sel.append(j)
        if len(sel) == k: break
    return sel


def main():
    os.makedirs(OUT, exist_ok=True)
    recs = {}
    for lab in ('env', 'target'):
        for r in (1, 2, 3):
            p = os.path.join(DATA, f'{lab}{r}.cs8')
            if not os.path.exists(p): continue
            meta = json.load(open(p[:-4] + '.json'))
            h = np.zeros(256, np.int64); psd, nseg, ns, sp = welch_stream(cs8_chunks(p, h))
            recs[f'{lab}{r}'] = dict(group=lab, src='openwrt', psd=psd, nseg=nseg, ns=ns, hist=h, segp=sp, meta=meta)
    ref_note = 'reference zip not found'
    if os.path.exists(REF):
        zf = zipfile.ZipFile(REF); ref_note = REF
        for m in zf.infolist():
            name = m.filename if m.flag_bits & 0x800 else m.filename.encode('cp437').decode('gbk')
            for key, lab in (('环境', 'env'), ('目标', 'target')):
                if name.endswith(key + '.wav'):
                    if m.CRC != REF_CRC[key]: ref_note += f'; WARNING {key} CRC differs from uploaded copy'
                    h = np.zeros(256, np.int64); psd, nseg, ns, sp = welch_stream(wav_chunks(zf, m, h))
                    recs['ref_' + lab] = dict(group=lab, src='reference', psd=psd, nseg=nseg, ns=ns, hist=h, segp=sp, meta={'file': name})
    keys = list(recs)
    edges = np.arange(-10e6, 10e6 + 1, 1e6)
    metrics, bands, pk = [], [], []
    for k in keys:
        r = recs[k]; d = db(r['psd']); c = local_contrast(d); r['db'] = d; r['c'] = c
        hist = r['hist']; tot = hist.sum()
        row = dict(record=k, source=r['src'], group=r['group'], samples=r['ns'], seconds=r['ns'] / FS, segments=r['nseg'],
                   band_power_db=float(db(r['psd'].sum() * df)),
                   power_excl_dc_db=float(db(r['psd'][np.abs(f) > 5000].sum() * df)),
                   seg_power_p10_db=float(np.percentile(db(r['segp']), 10)), seg_power_p90_db=float(np.percentile(db(r['segp']), 90)),
                   median_floor_db_per_hz=float(np.median(d)), codes_used=int((hist > 0).sum()),
                   mid_code_frac=float(hist[128] / tot), clip_frac=float((hist[0] + hist[255]) / tot),
                   rf_15MHz_band_db=float(db(r['psd'][(f >= -6e6) & (f < -4e6)].sum() * df)))
        metrics.append(row)
        for a, b in zip(edges[:-1], edges[1:]):
            m = (f >= a) & (f < b) & (np.abs(f) > 5000)
            bands.append(dict(record=k, rf_lo_mhz=(FC + a) / 1e6, rf_hi_mhz=(FC + b) / 1e6, power_db=float(db(r['psd'][m].sum() * df))))
        for rank, i in enumerate(peaks(c, d), 1):
            pk.append(dict(record=k, rank=rank, rf_mhz=round((FC + f[i]) / 1e6, 5), offset_hz=float(f[i]), contrast_db=round(float(c[i]), 2), psd_db=round(float(d[i]), 2)))

    def wcsv(name, rows):
        if not rows: return
        with io.open(os.path.join(OUT, name), 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    wcsv('metrics.csv', metrics); wcsv('bands.csv', bands); wcsv('peaks.csv', pk)
    cell = 328  # ~100 kHz
    nc = N // cell
    def cells(k): return db(recs[k]['psd'][:nc * cell].reshape(nc, cell).mean(1))
    fcell = f[:nc * cell].reshape(nc, cell).mean(1)
    summ = {'reference': ref_note}
    E = [k for k in keys if recs[k]['src'] == 'openwrt' and recs[k]['group'] == 'env']
    T = [k for k in keys if recs[k]['src'] == 'openwrt' and recs[k]['group'] == 'target']
    diff_rows = []
    if E and T:
        ce = np.array([cells(k) for k in E]); ct = np.array([cells(k) for k in T])
        diff = ct.mean(0) - ce.mean(0)
        sep = np.maximum(ct.min(0) - ce.max(0), ce.min(0) - ct.max(0))  # >0: ranges do not overlap
        within = np.maximum(np.ptp(ce, 0), np.ptp(ct, 0))
        for i in range(nc):
            diff_rows.append(dict(rf_mhz=round((FC + fcell[i]) / 1e6, 3), target_minus_env_db=round(float(diff[i]), 3),
                                  range_gap_db=round(float(sep[i]), 3), max_within_group_range_db=round(float(within[i]), 3)))
        wcsv('diff_cells.csv', diff_rows)
        ok = (sep > 1.0) & (np.abs(fcell) > 50e3)
        summ['cells_total'] = int(nc); summ['cells_separated_gt1dB'] = int(ok.sum())
        summ['cells_target_higher'] = int((ok & (diff > 0)).sum()); summ['cells_target_lower'] = int((ok & (diff < 0)).sum())
        top = np.argsort(-np.where(ok, np.abs(diff), -1))[:15]
        summ['top_separated_cells'] = [dict(rf_mhz=round((FC + fcell[i]) / 1e6, 3), diff_db=round(float(diff[i]), 2), gap_db=round(float(sep[i]), 2)) for i in top if ok[i]]
        corr = lambda a, b: float(np.corrcoef(a, b)[0, 1])
        lc = {k: recs[k]['c'][np.abs(f) > 5000] for k in keys}
        summ['local_contrast_corr'] = {f'{a}|{b}': round(corr(lc[a], lc[b]), 4) for a in keys for b in keys if a < b}
    summ['metrics'] = metrics
    for g, ks in (('env', E), ('target', T)):
        if not ks: continue
        base = [p for p in pk if p['record'] == ks[0]]
        rep = []
        for p in base:
            hit = sum(any(abs(q['offset_hz'] - p['offset_hz']) <= 10e3 for q in pk if q['record'] == k) for k in ks)
            other = [k for k in keys if recs[k]['group'] != g or recs[k]['src'] != 'openwrt']
            rep.append(dict(rf_mhz=p['rf_mhz'], contrast_db=p['contrast_db'], found_in_group=f'{hit}/{len(ks)}',
                            also_in=[k for k in other if any(abs(q['offset_hz'] - p['offset_hz']) <= 10e3 for q in pk if q['record'] == k)]))
        summ[f'peaks_{g}'] = rep
    rc = 64; nr = N // rc
    red = {k: db(recs[k]['psd'][:nr * rc].reshape(nr, rc).mean(1)) for k in keys}
    fr = f[:nr * rc].reshape(nr, rc).mean(1)
    with io.open(os.path.join(OUT, 'psd_reduced.csv'), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['rf_mhz'] + keys)
        for i in range(nr): w.writerow([round((FC + fr[i]) / 1e6, 4)] + [round(float(red[k][i]), 2) for k in keys])
    try:
        import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
        col = {'env': '#1f77b4', 'target': '#d62728'}
        fig, ax = plt.subplots(2, 1, figsize=(7.2, 5.2), sharex=True)
        for k in keys:
            ls = '-' if recs[k]['src'] == 'openwrt' else '--'
            a = ax[0] if recs[k]['src'] == 'openwrt' else ax[1]
            a.plot((FC + fr) / 1e6, red[k], ls, color=col[recs[k]['group']], lw=0.6, alpha=0.8, label=k)
        for a, t in zip(ax, ('New GL-MT3000 captures (LNA16/VGA4, amp off)', 'Reference ZIP (gain chain unknown)')):
            a.set_ylabel('PSD (dB, digital/Hz)'); a.set_title(t, fontsize=8); a.legend(fontsize=6, ncol=4); a.grid(alpha=.3)
        ax[1].set_xlabel('RF frequency (MHz), I+jQ assumed')
        fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig1_psd_overlay.png'), dpi=200); fig.savefig(os.path.join(OUT, 'fig1_psd_overlay.pdf')); plt.close(fig)
        if diff_rows:
            x = [r['rf_mhz'] for r in diff_rows]
            fig, ax = plt.subplots(figsize=(7.2, 2.8))
            ax.plot(x, [r['target_minus_env_db'] for r in diff_rows], 'k', lw=.7, label='target - env (mean of 3)')
            ax.fill_between(x, [-r['max_within_group_range_db'] for r in diff_rows], [r['max_within_group_range_db'] for r in diff_rows], color='gray', alpha=.3, label='+/- max within-group range')
            ax.set_xlabel('RF frequency (MHz)'); ax.set_ylabel('dB'); ax.legend(fontsize=7); ax.grid(alpha=.3)
            fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig2_difference.png'), dpi=200); fig.savefig(os.path.join(OUT, 'fig2_difference.pdf')); plt.close(fig)
        summ['figures'] = 'ok'
    except ImportError:
        summ['figures'] = 'matplotlib not installed; psd_reduced.csv written instead'
    json.dump(summ, open(os.path.join(OUT, 'summary.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('ANALYSIS_DONE', len(keys), 'records', summ.get('figures'), '|', ref_note)


if __name__ == '__main__':
    main()
