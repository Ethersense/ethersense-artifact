"""All ten measured positions, frozen first-position features, threshold sensitivity."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='4'
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import median_filter

BASE=Path(__file__).resolve().parents[1]
SRC=BASE.parent/'ethersense_supplemental'
OUT=BASE/'analysis/alongline';OUT.mkdir(parents=True,exist_ok=True)
def read(name):
    with (SRC/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
metrics=[r for r in read('quantitative_metrics.csv') if r['experiment']=='B']
features=[r for r in read('feature_tracking.csv') if r['record_id'].startswith('B')]
definitions=[r for r in read('feature_definitions.csv') if r['experiment']=='B']
assert len(metrics)==10 and len(features)==40 and len(definitions)==4
freqs=np.array([float(r['reference_offset_hz']) for r in definitions])
reference=np.load(SRC/'output/B01_spectra.npz')
frequency=reference['offset_hz'];step=float(frequency[1]-frequency[0])
baseline=np.load(SRC/'output/A09_spectra.npz')['mean_psd']
bgdb=10*np.log10(np.maximum(baseline,1e-30))
spectra={r['record_id']:np.load(SRC/('output/'+r['record_id']+'_spectra.npz'))['mean_psd'] for r in metrics}
sensitivity=[]
for bins in (101,201,401):
    bgcontrast=bgdb-median_filter(bgdb,size=bins,mode='nearest')
    for metric in metrics:
        pdb=10*np.log10(np.maximum(spectra[metric['record_id']],1e-30))
        contrast=pdb-median_filter(pdb,size=bins,mode='nearest')
        values=[]
        for ref in freqs:
            region=np.flatnonzero(np.abs(frequency-ref)<=5000+step)
            peak=region[np.argmax(pdb[region])]
            values.append((float(contrast[peak]),float(contrast[peak]-np.max(bgcontrast[region]))))
        for threshold in (3,6,10):
            kept=sum(c>=threshold and d>=threshold for c,d in values)
            sensitivity.append({'record_id':metric['record_id'],'distance_m':int(metric['distance_m']),
                                'median_bins':bins,'threshold_db':threshold,'reference_features':4,
                                'retained_features':kept,'reference_refitted':False})
write('all_positions_threshold_sensitivity.csv',sensitivity)
rows=[]
for metric in metrics:
    f=[r for r in features if r['record_id']==metric['record_id']]
    rows.append({'record_id':metric['record_id'],'position_m':int(metric['distance_m']),
                 'filename_time':metric['filename_time'],'duration_s':float(metric['duration_s']),
                 'power_central_10mhz_db_digital':float(metric['passband_power_db_digital_unit2']),
                 'power_relative_to_1m_db':float(metric['passband_power_db_digital_unit2'])-float(metrics[0]['passband_power_db_digital_unit2']),
                 'within_file_power_q10_db':float(metric['within_file_band_power_q10_db']),
                 'within_file_power_q90_db':float(metric['within_file_band_power_q90_db']),
                 'reference_features':4,'retained_6db':int(metric['features_retained_6db']),
                 'max_absolute_frequency_shift_hz':max(abs(float(x['frequency_shift_from_reference_hz'])) for x in f),
                 'minimum_peak_contrast_db':min(float(x['local_floor_contrast_db']) for x in f),
                 'maximum_peak_contrast_db':max(float(x['local_floor_contrast_db']) for x in f),
                 'independent_recordings_at_position':1})
write('measured_positions.csv',rows)
write('fixed_feature_tracking.csv',features)
by_feature=[]
for definition in definitions:
    group=[r for r in features if r['feature_id']==definition['feature_id']]
    by_feature.append({'feature_id':definition['feature_id'],'reference_offset_hz':float(definition['reference_offset_hz']),
                       'retained_positions':sum(r['feature_retained_at_6db_rule']=='True' for r in group),
                       'all_positions':len(group),
                       'minimum_local_contrast_db':min(float(r['local_floor_contrast_db']) for r in group),
                       'maximum_local_contrast_db':max(float(r['local_floor_contrast_db']) for r in group),
                       'maximum_frequency_shift_hz':max(abs(float(r['frequency_shift_from_reference_hz'])) for r in group)})
write('feature_summary.csv',by_feature)
power=[r['power_central_10mhz_db_digital'] for r in rows]
summary={'records':10,'positions_m':[r['position_m'] for r in rows],
         'frequency_grid_hz':step,'selected_first_position_features':4,
         'retained_features_by_position':[r['retained_6db'] for r in rows],
         'retained_feature_position_pairs':sum(r['retained_6db'] for r in rows),
         'total_feature_position_pairs':40,
         'features_retained_at_every_position':sum(r['retained_positions']==10 for r in by_feature),
         'power_span_db':max(power)-min(power),'power_10m_minus_1m_db':power[-1]-power[0],
         'maximum_recorded_feature_shift_hz':max(r['max_absolute_frequency_shift_hz'] for r in rows),
         'first_record_within_file_q90_minus_q10_db':float(metrics[0]['within_file_band_power_q90_minus_q10_db']),
         'first_record_last_minus_first_temporal_bin_db':float(metrics[0]['last_vs_first_temporal_bin_db']),
         'sensitivity_10m':[r for r in sensitivity if r['distance_m']==10],
         'interpretation':'Three fixed spectral locations remain observable at all ten along-line positions while amplitudes vary non-monotonically. This supports structural feature tracking in this deployment; it does not identify the coupling path, supply appliance-specific OFF evidence, or constitute a cable-length intervention.',
         'limitations':['One sequential recording per position, position/time confounded',
                        'Gain and channel order not independently documented',
                        'A09 is a preceding base, not a verified charger-OFF record',
                        'The 16 temporal bins are within-record fluctuations, not independent spatial repetitions',
                        'These are receiver positions along an existing line, not appliance cord lengths'],
         'source_manifest':{str(p.relative_to(SRC)):hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in [SRC/'quantitative_metrics.csv',SRC/'feature_tracking.csv',SRC/'feature_definitions.csv',SRC/'output/A09_spectra.npz',*[SRC/('output/B%02d_spectra.npz'%i) for i in range(1,11)]]}}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('source_manifest','sensitivity_10m','limitations')},ensure_ascii=False,indent=2))
