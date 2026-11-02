"""Check fixed reference locations against an existing, separately recorded environment."""
import csv,json
from pathlib import Path
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks
from analysis_helpers import BASE,make_psd,sha
legacy=BASE/'raw/legacy_environment'
metadata=json.loads((legacy/'env1.json').read_text(encoding='utf-8-sig'))
raw=legacy/'env1.cs8'
assert sha(raw)==metadata['sha256'] and raw.stat().st_size==metadata['expected_bytes']==40000000
freq,psd,details=make_psd(raw)
db=10*np.log10(np.maximum(psd,1e-30));contrast=db-median_filter(db,size=201,mode='nearest')
template=json.loads((BASE/'analysis/fixed_template.json').read_text(encoding='utf-8'))
peaks,_=find_peaks(db,prominence=3,distance=8);peaks=peaks[contrast[peaks]>=6]
rows=[]
for ref in template['reference_frequency_offset_hz']:
    choices=peaks[np.abs(freq[peaks]-ref)<=5000]
    selected=choices[np.argmin(np.abs(freq[choices]-ref))] if len(choices) else np.argmin(np.abs(freq-ref))
    rows.append({'fixed_reference_offset_hz':ref,'legacy_observed_offset_hz':float(freq[selected]),
                 'legacy_local_contrast_db':float(contrast[selected]),'matched_6db_prominence3db_within5khz':bool(len(choices))})
with open(BASE/'analysis/reference_specificity.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
record={'legacy_record':'20261019_ab/env1.cs8','legacy_sha256':metadata['sha256'],
        'all_matched':all(r['matched_6db_prominence3db_within5khz'] for r in rows),
        'rows':rows,'interpretation':'An earlier environment recording is not a contemporaneous OFF control; line coincidence undermines target-specific interpretation of the four-peak probe. It does not identify the physical origin of these lines or allow cross-session calibrated-power comparisons.'}
(BASE/'analysis/reference_specificity.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
np.savez_compressed(BASE/'analysis/legacy_environment_psd.npz',offset_hz=freq,psd=psd,contrast_db=contrast)
print(json.dumps(record,indent=2))
