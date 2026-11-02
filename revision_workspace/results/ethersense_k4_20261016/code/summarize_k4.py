"""Compact evidence tables from the completed, raw-derived K4 analysis."""
from __future__ import annotations
import csv
import json
import runtime_limits
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.signal import find_peaks
from audit_k4 import table_write
from analyze_k4 import finite_json,summarize

ROOT=Path(__file__).resolve().parent.parent


def read(name):
    with (ROOT/name).open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))


def num(r,k):
    v=r.get(k,'');return float(v) if v not in ('',None) else np.nan


def main():
    s=json.loads((ROOT/'analysis_summary.json').read_text(encoding='utf-8'))
    inv=json.loads((ROOT/'data_inventory.json').read_text(encoding='utf-8'))
    records=read('record_metrics.csv');features=read('feature_tracking.csv');pairs=read('pairwise_similarity.csv')
    definitions=read('feature_definitions.csv');conditions=read('cable_condition_statistics.csv')
    primary=set(s['cable']['main_record_ids']);out={}
    for group in ('stability','cable'):
        rr=[r for r in records if r['experiment']==group]
        fields=['full_band_power_db','reference_log_psd_correlation','reference_local_contrast_correlation',
                'template_peak_presence_score','storage_mid_code_fraction','occupied_storage_codes','within_file_band_db_q90_minus_q10']
        out[group]={key:summarize([num(r,key) for r in rr]) for key in fields}
        out[group]['n_recordings']=len(rr)
        out[group]['power_range_db']=out[group]['full_band_power_db']['maximum']-out[group]['full_band_power_db']['minimum']
        present=[r for r in features if r['experiment']==group and r['detected_above6db']=='True']
        out[group]['detected_feature_rows']=len(present)
        out[group]['feature_rows']=sum(r['experiment']==group for r in features)
        out[group]['max_abs_detected_displacement_hz']=max([abs(num(r,'frequency_shift_hz_if_detected')) for r in present],default=None)
    out['cable_main']={key:summarize([num(r,key) for r in records if r['record_id'] in primary]) for key in fields}
    out['cable_main']['within_condition_corr']=summarize([num(r,'local_contrast_correlation') for r in pairs if r['group']=='cable_main' and r['same_wire_condition']=='True'])
    out['cable_main']['between_condition_corr']=summarize([num(r,'local_contrast_correlation') for r in pairs if r['group']=='cable_main' and r['same_wire_condition']=='False'])
    threshold=[];peak_stats=[];derived=np.load(ROOT/'derived_spectra.npz')
    for group in ('stability','cable'):
        bank=[r for r in definitions if r['experiment']==group]
        for definition in bank:
            rr=[r for r in features if r['feature_id']==definition['feature_id'] and r['experiment']==group]
            present=[r for r in rr if r['detected_above6db']=='True']
            peak_stats.append({'experiment':group,'feature_id':definition['feature_id'],'reference_offset_hz':num(definition,'reference_offset_hz'),
                'nominal_rf_hz_IQ':num(definition,'nominal_rf_hz_IQ'),'nominal_rf_hz_QI':num(definition,'nominal_rf_hz_QI'),
                'detected_records':len(present),'total_records':len(rr),'max_abs_detected_displacement_hz':max([abs(num(r,'frequency_shift_hz_if_detected')) for r in present],default=None),
                'local_contrast_min_db':min([num(r,'local_floor_contrast_db') for r in present],default=None),
                'local_contrast_max_db':max([num(r,'local_floor_contrast_db') for r in present],default=None),
                'relative_peak_min_db':min([num(r,'relative_peak_amplitude_db') for r in present],default=None),
                'relative_peak_max_db':max([num(r,'relative_peak_amplitude_db') for r in present],default=None),
                'within_capture_presence_min':min([num(r,'within_file_presence_fraction6db') for r in present],default=None),
                'source_attribution':'candidate only; mirrored peaks not independent sources'})
        for rid in [r['record_id'] for r in records if r['experiment']==group]:
            rr=[r for r in features if r['record_id']==rid]
            f=derived[rid+'__f'];psd=derived[rid+'__psd'];contrast=derived[rid+'__contrast'];df=float(f[1]-f[0])
            for t in (3,6,10):
                local,_=find_peaks(contrast,height=t,prominence=3,distance=7);found=0
                for row in rr:
                    target=num(row,'target_offset_hz_in_this_record');candidates=local[np.abs(f[local]-target)<=5000]
                    if len(candidates):
                        k=candidates[np.argmax(psd[candidates])];found+=int(abs(f[k]-target)<5000-df)
                threshold.append({'record_id':rid,'experiment':group,'threshold_db':t,'retained_candidates':found,'candidate_count':len(rr),'presence_score':found/len(rr) if rr else None,
                    'interpretation':'conditional on fixed 6dB-selected reference bank; not a reselected detector or accuracy'})
    cable_feature_conditions=[]
    for condition in conditions:
        for definition in (r for r in definitions if r['experiment']=='cable'):
            rr=[r for r in features if r['experiment']=='cable' and r['geometry']==condition['geometry'] and r['distance_label_cm']==condition['distance_label_cm'] and r['feature_id']==definition['feature_id']]
            present=[r for r in rr if r['detected_above6db']=='True'];delta=[num(r,'frequency_shift_hz_if_detected') for r in present]
            cable_feature_conditions.append({'geometry':condition['geometry'],'distance_label_cm':int(condition['distance_label_cm']),'feature_id':definition['feature_id'],
                'n_technical_recordings':len(rr),'detected_recordings':len(present),'mean_detected_shift_hz':np.mean(delta) if delta else None,
                'detected_shift_range_hz':max(delta)-min(delta) if delta else None,'mean_local_contrast_db':np.mean([num(r,'local_floor_contrast_db') for r in present]) if present else None,
                'sd_local_contrast_db':np.std([num(r,'local_floor_contrast_db') for r in present],ddof=1) if len(present)>1 else None,
                'mean_relative_peak_db':np.mean([num(r,'relative_peak_amplitude_db') for r in present]) if present else None,
                'sd_relative_peak_db':np.std([num(r,'relative_peak_amplitude_db') for r in present],ddof=1) if len(present)>1 else None,
                'attribution':'not source-verified; undetected means outside/inadequate match within declared search window'})
    group_pairs=[]
    for a,b in [('c40','s40'),('c80','s80'),('c40','c80'),('s40','s80')]:
        def cond_id(rid):
            r=next(x for x in inv['records'] if x['record_id']==rid);return r['geometry']+str(r['distance_label_cm'])
        pp=[r for r in pairs if r['group']=='cable_main' and {cond_id(r['record_a']),cond_id(r['record_b'])}=={a,b}]
        group_pairs.append({'comparison':a+'_vs_'+b,'n_record_pairs':len(pp),**summarize([num(r,'local_contrast_correlation') for r in pp]),'independence':'16 pair scores reuse 4+4 recordings; not16 independent trials'})
    out['cable_condition_pair_correlations']=group_pairs
    out['stability']['pair_log_corr']=s['stability']['log_psd_pair_correlation'];out['stability']['pair_local_corr']=s['stability']['local_contrast_pair_correlation']
    out['stability']['verified_date_count']=s['stability']['confirmed_date_count']
    out['max_reference_welch_relative_error']=s['max_reference_welch_relative_error']
    out['peak_statistics']=peak_stats
    out['raw_integrity']={'all_crc_passed':s['raw_crc_all_passed'],'duplicate_content_groups':s['content_duplicates'],'compute_seconds':s['compute_wall_seconds']}
    table_write(ROOT/'peak_summary.csv',[finite_json(r) for r in peak_stats])
    table_write(ROOT/'threshold_sensitivity.csv',[finite_json(r) for r in threshold])
    table_write(ROOT/'cable_peak_condition_statistics.csv',[finite_json(r) for r in cable_feature_conditions])
    table_write(ROOT/'cable_condition_pair_correlations.csv',[finite_json(r) for r in group_pairs])
    (ROOT/'evidence_summary.json').write_text(json.dumps(finite_json(out),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(finite_json({k:v for k,v in out.items() if k!='peak_statistics'}),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
