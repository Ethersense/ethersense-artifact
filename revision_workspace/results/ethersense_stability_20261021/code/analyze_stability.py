"""Fixed Day-1 spectral diagnostics. No classifier retraining or negative-class inference."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='4'
import csv, hashlib, json
from pathlib import Path
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks
OUT=Path(__file__).resolve().parents[1]
A=OUT/'analysis';A.mkdir(exist_ok=True)
inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
records=inv['records'];rows=[];spectra=[];contrasts=[];band_profiles=[];peaksets=[]
for r in records:
    rid=r['record_id'];z=np.load(OUT/'welch'/(rid+'_spectra.npz'))
    q=json.loads((OUT/'welch'/(rid+'_quality.json')).read_text(encoding='utf-8'))
    deep=json.loads((OUT/'deep'/(rid+'_deep.json')).read_text(encoding='utf-8'))
    assert q['full_zip_crc_validated'] and deep['crc_ok']
    f=z['offset_hz'].astype(float);df=f[1]-f[0]
    # Average full-record Welch is the primary spectrum; median of 16 temporal sections is a separate diagnostic.
    p=z['mean_psd'].astype(float);db=10*np.log10(np.maximum(p,1e-30))
    c=db-median_filter(db,size=201,mode='nearest')
    mask=(np.abs(f)>5e3)&(np.abs(f)<9.95e6)
    peaks,props=find_peaks(c,height=6,prominence=3,distance=3)
    peaks=peaks[mask[peaks]]
    band=np.array([10*np.log10(p[(f>=b*1e6)&(f<(b+1)*1e6)&(np.abs(f)>5e3)].sum()*df) for b in range(-10,10)])
    x=np.clip(c,0,None);x[~mask]=0;x-=x.mean()
    ac=np.fft.irfft(np.abs(np.fft.rfft(x,n=2*len(x)))**2)[:len(x)];ac/=ac[0]
    lo,hi=int(3e3/df),int(600e3/df);k=lo+int(np.argmax(ac[lo:hi]))
    hist=np.array(q['storage_histogram_8bit']);counts=np.flatnonzero(hist)
    rows.append(dict(record_id=rid,date=r['date'],day=r['day'],file=r['file_name'],state=r['state'],seconds=r['duration_s'],
        full_power_db=10*np.log10(p.sum()*df),comb_khz=k*df/1000,comb_strength=ac[k],
        modulation_100_index=deep['full_harm'][1],modulation_100_snr=deep['full_100_snr'],apparent_mains_hz=deep['mains_hz'],
        adc_codes=len(counts),code_min=int(counts.min()),code_max=int(counts.max()),
        central_code_fraction=hist[128]/hist.sum(),endpoint_fraction=q['pcm_endpoint_fraction'],
        crc_ok=True,sha256_wav=q['sha256_uncompressed_wav'],reference_welch_error=q['reference_welch_relative_error']))
    spectra.append(p);contrasts.append(c);band_profiles.append(band);peaksets.append(peaks)
P=np.array(spectra);C=np.array(contrasts);B=np.array(band_profiles)
# The candidate list, selection criteria, matching tolerance and threshold use Day 1 only.
ref_candidates=peaksets[0]
ref_candidates=ref_candidates[np.argsort(C[0,ref_candidates])[::-1]][:20]
assert len(ref_candidates)>0,'No Day-1 candidates at the prespecified threshold; do not weaken it post hoc.'
peak_rows=[]
for i,r in enumerate(rows):
    matched=[];shifts=[]
    for j,pk in enumerate(ref_candidates):
        possible=peaksets[i][np.abs(f[peaksets[i]]-f[pk])<=5e3]
        if len(possible):
            candidate=possible[np.argmin(np.abs(f[possible]-f[pk]))]
            displacement=f[candidate]-f[pk];matched.append(int(candidate));shifts.append(float(displacement))
            peak_rows.append(dict(date=r['date'],candidate=j+1,reference_offset_hz=f[pk],observed_offset_hz=f[candidate],
                offset_change_hz=displacement,contrast_db=C[i,candidate],retained=True))
        else:peak_rows.append(dict(date=r['date'],candidate=j+1,reference_offset_hz=f[pk],observed_offset_hz='',offset_change_hz='',contrast_db='',retained=False))
    r.update(day1_candidates=len(ref_candidates),retained_candidates=len(matched),retention_fraction=len(matched)/len(ref_candidates),
        max_abs_peak_shift_hz=max(map(abs,shifts)) if shifts else None,
        day1_log_psd_correlation=float(np.corrcoef(np.log10(P[0,mask]),np.log10(P[i,mask]))[0,1]),
        day1_local_contrast_correlation=float(np.corrcoef(C[0,mask],C[i,mask])[0,1]),
        day1_1mhz_profile_correlation=float(np.corrcoef(B[0],B[i])[0,1]),
        day1_1mhz_profile_rms_db=float(np.sqrt(np.mean((B[i]-B[0])**2))))
def write_csv(name,data):
    with (A/name).open('w',encoding='utf-8-sig',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
write_csv('daily_metrics.csv',rows);write_csv('fixed_day1_peaks.csv',peak_rows)
write_csv('band_profiles.csv',[dict(date=r['date'],offset_start_mhz=b,power_db=B[i,j]) for i,r in enumerate(rows) for j,b in enumerate(range(-10,10))])
def rg(key,subset=None):
    rr=rows if subset is None else subset
    return [min(r[key] for r in rr),max(r[key] for r in rr)]
summary=dict(record_count=len(rows),date_count=len({r['date'] for r in rows}),first_date=rows[0]['date'],last_date=rows[-1]['date'],
    elapsed_days=rows[-1]['day']-rows[0]['day'],one_record_per_day=True,all_crc_ok=all(r['crc_ok'] for r in rows),
    full_power_db_range=rg('full_power_db'),full_power_span_db=float(np.ptp([r['full_power_db'] for r in rows])),
    comb_khz_range=rg('comb_khz'),comb_strength_range=rg('comb_strength'),modulation_100_index_range=rg('modulation_100_index'),
    modulation_100_snr_range=rg('modulation_100_snr'),apparent_mains_hz_range=rg('apparent_mains_hz'),adc_code_count_range=rg('adc_codes'),
    central_code_fraction_range=rg('central_code_fraction'),endpoint_fraction_max=max(r['endpoint_fraction'] for r in rows),
    fixed_day1_candidate_count=len(ref_candidates),retained_candidates_range=rg('retained_candidates'),
    retention_fraction_range=rg('retention_fraction'),max_abs_peak_shift_hz=max(r['max_abs_peak_shift_hz'] for r in rows if r['max_abs_peak_shift_hz'] is not None),
    heldout_date_count=len(rows)-1,heldout_log_psd_correlation_range=rg('day1_log_psd_correlation',rows[1:]),
    heldout_local_contrast_correlation_range=rg('day1_local_contrast_correlation',rows[1:]),
    heldout_1mhz_profile_correlation_range=rg('day1_1mhz_profile_correlation',rows[1:]),
    heldout_1mhz_profile_rms_db_range=rg('day1_1mhz_profile_rms_db',rows[1:]),
    candidate_selection='Day 1 only: local contrast >=6 dB above 201-bin median; prominence >=3 dB; top 20 by contrast; match nearest qualifying peak within +/-5 kHz; DC +/-5 kHz and edge 50 kHz excluded.',
    fft_bins_hz=df,method='Full-record Hann Welch N=65536, 50% overlap, per-window mean removed. Digital dB, not dBm.',
    state_scope='One heater, positive records only; no fresh multiclass accuracy, negative-class specificity, or month/year robustness is inferred.',
    max_reference_welch_relative_error=max(r['reference_welch_error'] for r in rows))
(A/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
np.savez_compressed(A/'spectral_features.npz',offset_hz=f,mean_psd=P,local_contrast_db=C,band_profiles_db=B,
    dates=np.array([r['date'] for r in rows]),reference_peak_offsets_hz=f[ref_candidates])
print(json.dumps(summary,ensure_ascii=False,indent=2))
