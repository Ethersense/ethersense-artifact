"""Apply the pre-fixed probe unchanged to every completed trial."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='4'
import csv
import json
from pathlib import Path
import re
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks
from analysis_helpers import BASE,make_psd,sha,verify

TEMPLATE=json.loads((BASE/'analysis/fixed_template.json').read_text(encoding='utf-8'))
fixed=np.array(TEMPLATE['reference_frequency_offset_hz'])
run=sorted(p for p in (BASE/'raw').glob('wifi_detection_*') if p.is_dir())[-1]
reference=np.load(BASE/'analysis/reference_psd.npz')
reference_db=10*np.log10(np.maximum(reference['psd'],1e-30))
rows=[];feature_rows=[]
psds={};health=[]
def read_json(path):
    if not path.exists():return None
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError:return None
for trial in sorted(run.iterdir()):
    raw=trial/'capture.cs8'
    if not raw.exists() or not (trial/'desktop_verified.json').exists():continue
    cached=BASE/'analysis'/(trial.name+'_psd.npz')
    if cached.exists():
        d=np.load(cached);freq=d['offset_hz'];psd=d['psd'];contrast=d['contrast_db']
    else:
        freq,psd,_=make_psd(raw)
        db=10*np.log10(np.maximum(psd,1e-30))
        contrast=db-median_filter(db,size=201,mode='nearest')
        np.savez_compressed(cached,offset_hz=freq,psd=psd,contrast_db=contrast)
    db=10*np.log10(np.maximum(psd,1e-30));df=freq[1]-freq[0]
    peaks,_=find_peaks(db,prominence=3,distance=8)
    qualifying=peaks[contrast[peaks]>=6]
    kept=0;contrasts=[];shifts=[]
    for i,ref in enumerate(fixed):
        candidates=qualifying[np.abs(freq[qualifying]-ref)<=5000]
        if len(candidates):
            selected=candidates[np.argmin(abs(freq[candidates]-ref))];match=True;kept+=1
        else:
            region=np.flatnonzero(np.abs(freq-ref)<=5000)
            selected=region[np.argmax(db[region])];match=False
        contrasts.append(float(contrast[selected]));shifts.append(float(freq[selected]-ref))
        feature_rows.append({'trial':trial.name,'feature':i+1,'reference_offset_hz':float(ref),
                             'observed_offset_hz':float(freq[selected]),'shift_hz':float(freq[selected]-ref),
                             'local_floor_contrast_db':float(contrast[selected]),'matched':bool(match)})
    codes=np.memmap(raw,dtype=np.int8,mode='r').reshape(-1,2)
    counts=np.bincount(codes.ravel().astype(np.int16)+128,minlength=256)
    settings=dict(re.findall(r'(\w+)=([^\s]+)',(trial/'settings.txt').read_text(encoding='ascii')))
    health_lines=(trial/'health.log').read_text(encoding='ascii').splitlines()
    temperatures=[int(x) for line in health_lines for x in re.findall(r'max_temp_mc=(\d+)',line)]
    health+=temperatures
    start=float((trial/'capture_start_uptime.txt').read_text().split()[0]);end=float((trial/'capture_end_uptime.txt').read_text().split()[0])
    tx_before=int((trial/'tx_packets_before.txt').read_text());tx_after=int((trial/'tx_packets_after.txt').read_text())
    server=read_json(trial/'server.json');client=read_json(trial/'iperf.json')
    receive={};sender={}
    if server:receive=server.get('end',{}).get('sum_received',server.get('end',{}).get('sum',{}))
    if client:sender=client.get('end',{}).get('sum',{})
    if not receive and client:
        receive=client.get('end',{}).get('sum_received',{})
    band=(np.abs(freq)>20000)&(np.abs(freq)<9_950_000)
    power=float(10*np.log10(psd[band].sum()*df))
    row={'trial':trial.name,'is_independent_reference':trial.name=='REF_idle',
         'offered_mbps':int(settings['offered_mbps']),'received_mbps':receive.get('bits_per_second',0)/1e6,
         'sent_mbps':sender.get('bits_per_second',0)/1e6,
         'received_udp_payload_pps':receive.get('bytes',0)/1200/receive.get('seconds',1),
         'receiver_packets':receive.get('packets'),'receiver_lost_packets':receive.get('lost_packets'),
         'receiver_loss_percent':receive.get('lost_percent'),
         'capture_wall_seconds':end-start,'interface_tx_packet_delta_during_capture':tx_after-tx_before,
         'capture_start_after_traffic_start_s':start-float((trial/'iperf_start_uptime.txt').read_text().split()[0]),
         'interface_tx_pps_during_capture':(tx_after-tx_before)/(end-start),
         'reference_peak_count':len(fixed),'matched_peaks':kept,
         'template_pass_at_80percent':kept/len(fixed)>=.8,
         'minimum_reference_peak_contrast_db':min(contrasts),
         'maximum_reference_peak_shift_hz':max(abs(x) for x in shifts),
         'log_psd_correlation_to_reference':float(np.corrcoef(reference_db[band],db[band])[0,1]),
         'non_dc_digital_power_db':power,
         'unique_signed_codes':int(np.count_nonzero(counts)),
         'endpoint_fraction':float((counts[0]+counts[-1])/counts.sum()),
         'i_mean_codes':float(codes[:,0].mean()),'q_mean_codes':float(codes[:,1].mean()),
         'max_temp_celsius':max(temperatures)/1000,'raw_bytes':raw.stat().st_size,
         'raw_sha256':sha(raw)}
    rows.append(row);psds[trial.name]=psd
if not rows:raise SystemExit('No completed verified records')
def write(name,rs):
    with (BASE/'analysis'/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
write('wifi_trial_metrics.csv',rows);write('wifi_peak_tracking.csv',feature_rows)
formal=[r for r in rows if not r['is_independent_reference']]
groups=[]
for rate in (0,5,25):
    group=[r for r in formal if r['offered_mbps']==rate]
    if not group:continue
    groups.append({'offered_mbps':rate,'trials':len(group),
                   'template_passes':sum(r['template_pass_at_80percent'] for r in group),
                   'matched_peaks':[r['matched_peaks'] for r in group],
                   'median_received_mbps':float(np.median([r['received_mbps'] for r in group])),
                   'received_mbps_range':[min(r['received_mbps'] for r in group),max(r['received_mbps'] for r in group)],
                   'sent_mbps_range':[min(r['sent_mbps'] for r in group),max(r['sent_mbps'] for r in group)],
                   'received_udp_payload_pps_range':[min(r['received_udp_payload_pps'] for r in group),max(r['received_udp_payload_pps'] for r in group)],
                   'loss_percent_range':([min(r['receiver_loss_percent'] for r in group),max(r['receiver_loss_percent'] for r in group)] if rate else None),
                   'interface_tx_pps_range':[min(r['interface_tx_pps_during_capture'] for r in group),max(r['interface_tx_pps_during_capture'] for r in group)],
                   'digital_power_db_range':[min(r['non_dc_digital_power_db'] for r in group),max(r['non_dc_digital_power_db'] for r in group)],
                   'log_psd_correlation_range':[min(r['log_psd_correlation_to_reference'] for r in group),max(r['log_psd_correlation_to_reference'] for r in group)]})
global_health=(run/'health.log').read_text(encoding='utf-8-sig')
global_temps=[int(v) for v in re.findall(r'max_temp_mc=(\d+)',global_health)]
global_uptime=[int(v) for v in re.findall(r'uptime_s=(\d+)',global_health)]
health+=global_temps
boot_ids={(p/'boot_id.txt').read_text().strip() for p in run.iterdir() if (p/'boot_id.txt').exists()}
summary={'run':run.name,'completed_records':len(rows),'formal_records':len(formal),'groups':groups,
         'independent_reference_sha256':TEMPLATE['reference_sha256'],
         'fixed_reference_offsets_hz':fixed.tolist(),
         'maximum_temperature_celsius':max(health)/1000,
         'host_health_samples':len(global_temps),
         'host_health_minimum_temperature_celsius':min(global_temps)/1000,
         'host_uptime_monotonic':all(a<=b for a,b in zip(global_uptime,global_uptime[1:])),
         'trial_boot_id_count':len(boot_ids),'trial_boot_id':next(iter(boot_ids)) if len(boot_ids)==1 else None,
         'raw_bytes_all_new_captures':sum(r['raw_bytes'] for r in rows),
         'whole_record_log_psd_correlations':[min(r['log_psd_correlation_to_reference'] for r in formal),max(r['log_psd_correlation_to_reference'] for r in formal)],
         'all_expected_records_downloaded':len(rows)==10,
         'router_runner_all_done':(run/'ALL_DONE').exists(),
         'target_identity':'not confirmed by physical operator',
         'external_lna_power':'not remotely verifiable',
         'source_specificity':'Not established. Symmetric reference lines at exact sample-clock fractions may include receiver or other apparatus spurs. No current matched OFF capture or validated full classifier is available.',
         'conclusion_scope':'Fixed-deployment spectral consistency under measured Wi-Fi load; not a multiclass accuracy, appliance-specific detection probability, or false-positive experiment.'}
(BASE/'analysis/wifi_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
