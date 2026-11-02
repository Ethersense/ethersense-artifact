"""K4 descriptive statistics: keep RF bands and technical/date units separate."""
from __future__ import annotations

import csv
import hashlib
import json
import runtime_limits
from collections import Counter, defaultdict
from datetime import date as calendar_date, timedelta
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks

from audit_k4 import table_write

ROOT=Path(__file__).resolve().parent.parent


def db(x): return 10*np.log10(np.maximum(x,np.finfo(float).tiny))


def finite_json(obj):
    if isinstance(obj,dict): return {k:finite_json(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)): return [finite_json(v) for v in obj]
    if isinstance(obj,np.ndarray): return finite_json(obj.tolist())
    if isinstance(obj,(np.bool_,)): return bool(obj)
    if isinstance(obj,(np.integer,)): return int(obj)
    if isinstance(obj,(float,np.floating)): return float(obj) if np.isfinite(obj) else None
    return obj


def corr(x,y):
    ok=np.isfinite(x)&np.isfinite(y)
    if ok.sum()<3 or np.std(x[ok])==0 or np.std(y[ok])==0: return float("nan")
    return float(np.corrcoef(x[ok],y[ok])[0,1])


def summarize(values):
    v=np.asarray(values,float);v=v[np.isfinite(v)]
    return {"n":len(v),"mean":float(v.mean()) if len(v) else None,"sd":float(v.std(ddof=1)) if len(v)>1 else None,"minimum":float(v.min()) if len(v) else None,"maximum":float(v.max()) if len(v) else None}


def aligned(a,b,field):
    """Return physically aligned spectra; never combine two experiment types."""
    ra,rb=a["r"],b["r"]
    if ra["experiment"]!=rb["experiment"]: raise ValueError("Cross-band stability/cable mixing is forbidden")
    if ra["center_frequency_hz"]==rb["center_frequency_hz"] and np.array_equal(a["f"],b["f"]) and ra.get("iq_order")==rb.get("iq_order"):
        valid=a["band"]&b["band"]&(np.abs(a["f"])>5000)
        return a[field][valid],b[field][valid]
    def rf(d):
        order=d["r"].get("iq_order")
        if order not in ("I+jQ","Q+jI","I-jQ"):
            raise ValueError("Changed centers/sample grids require confirmed I/Q RF orientation")
        sign=1 if order=="I+jQ" else -1
        return d["r"]["center_frequency_hz"]+sign*d["f"]
    fa,fb=rf(a),rf(b)
    lower=max(fa[a["band"]].min(),fb[b["band"]].min());upper=min(fa[a["band"]].max(),fb[b["band"]].max())
    step=max(a["df"],b["df"]);grid=np.arange(lower,upper+step*.1,step)
    if len(grid)<100: raise ValueError("Insufficient common RF coverage")
    keep=(np.abs(grid-ra["center_frequency_hz"])>5000)&(np.abs(grid-rb["center_frequency_hz"])>5000)
    grid=grid[keep]
    ia,ib=np.argsort(fa),np.argsort(fb)
    return np.interp(grid,fa[ia],a[field][ia]),np.interp(grid,fb[ib],b[field][ib])


def daily_analysis(records,stable_ids,enrollment_date=None):
    """Actual calendar dates only; Day 1 template is a mean of Day 1 recordings.

    Different grids are aligned on the coarsest common RF grid. No negative class
    exists: output correlation/peak-presence scores, never accuracy or Macro-F1.
    """
    groups=defaultdict(list)
    for rid in stable_ids:
        r=records[rid]['r']
        if r['acquisition_date']: groups[r['acquisition_date']].append(rid)
    if not groups: return [],[],{},{}
    ids=[rid for g in groups.values() for rid in g];first=records[ids[0]]
    native=all(records[rid]['r']['center_frequency_hz']==first['r']['center_frequency_hz'] and
               records[rid]['r'].get('iq_order')==first['r'].get('iq_order') and
               np.array_equal(records[rid]['f'],first['f']) for rid in ids)
    if native:
        axis=first['f'];kind='encoded_offset_hz'
        spectra={rid:records[rid]['psd'] for rid in ids}
    else:
        axes={}
        for rid in ids:
            d=records[rid];order=d['r'].get('iq_order')
            if order not in ('I+jQ','Q+jI','I-jQ'): raise ValueError('Daily RF alignment needs confirmed I/Q order')
            axes[rid]=d['r']['center_frequency_hz']+(1 if order=='I+jQ' else -1)*d['f']
        lower=max(axes[rid][records[rid]['band']].min() for rid in ids)
        upper=min(axes[rid][records[rid]['band']].max() for rid in ids)
        step=max(records[rid]['df'] for rid in ids);axis=np.arange(lower,upper+step*.1,step);kind='rf_hz'
        if len(axis)<100: raise ValueError('Insufficient common daily frequency coverage')
        spectra={rid:np.interp(axis,np.sort(axes[rid]),records[rid]['psd'][np.argsort(axes[rid])]) for rid in ids}
    dates=sorted(groups)
    if enrollment_date and enrollment_date!=dates[0]:
        raise ValueError('Confirmed Day1 enrollment must be the earliest date of this reviewed cohort; review cohort/date mapping')
    day1_confirmed=bool(enrollment_date) or any(str(records[rid]['r'].get('relative_day_confirmed'))=='1' for rid in groups[dates[0]])
    day_psd=np.array([np.mean([spectra[rid] for rid in groups[date]],axis=0) for date in dates])
    day_db=db(day_psd);day_floor=median_filter(day_db,size=(1,201),mode='nearest');day_contrast=day_db-day_floor
    valid=np.ones(len(axis),bool)
    for rid in ids:
        center=0 if native else records[rid]['r']['center_frequency_hz'];valid &= np.abs(axis-center)>5000
    candidates,_=find_peaks(day_contrast[0],height=6,prominence=3,distance=7)
    bank=[]
    for i in sorted(candidates,key=lambda i:day_contrast[0,i],reverse=True):
        if not valid[i] or i<164 or i>=len(axis)-164: continue
        if all(abs(axis[i]-axis[j])>10000 for j in bank): bank.append(int(i))
        if len(bank)==8: break
    day_rows=[];pair_rows=[]
    for j,date in enumerate(dates):
        detected=0
        day_peaks,_=find_peaks(day_contrast[j],height=6,prominence=3,distance=7)
        for i in bank:
            local=day_peaks[np.abs(axis[day_peaks]-axis[i])<=5000]
            if len(local):
                k=local[np.argmax(day_psd[j,local])]
                detected+=int(abs(axis[k]-axis[i])<5000-(axis[1]-axis[0]))
        day_rows.append({'acquisition_date':date,'recordings':len(groups[date]),'reference_date':dates[0],
                         'reference_is_confirmed_experiment_day1':day1_confirmed,'day1_date':dates[0] if day1_confirmed else None,
                         'daily_mean_template_log_psd_corr':corr(day_db[0,valid],day_db[j,valid]),
                         'daily_mean_template_local_corr':corr(day_contrast[0,valid],day_contrast[j,valid]),
                         'reference_candidate_count':len(bank),'reference_peak_presence_score':detected/len(bank) if bank else None,
                         'day1_mean_candidate_count':len(bank) if day1_confirmed else None,'day1_mean_peak_presence_score':detected/len(bank) if bank and day1_confirmed else None,
                         'within_day_independent_record_pair_count':len(groups[date])*(len(groups[date])-1)//2,
                         'interpretation':'descriptive scores; earliest available date is not assumed to be experiment Day1; no negative classes'})
        for k in range(j):
            pair_rows.append({'date_a':dates[k],'date_b':date,'log_psd_correlation':corr(day_db[k,valid],day_db[j,valid]),
                              'local_contrast_correlation':corr(day_contrast[k,valid],day_contrast[j,valid])})
    meta={'dates':dates,'axis_kind':kind,'reference_date':dates[0],'reference_is_confirmed_experiment_day1':day1_confirmed,
          'day1_date':dates[0] if day1_confirmed else None,'reference_candidate_indices':bank,
          'note':'Daily mean averages captures, not a multi-class recognition experiment; unknown dates are excluded'}
    arrays={'daily_axis_hz':axis,'daily_psd':day_psd,'daily_psd_db':day_db,'daily_local_contrast':day_contrast}
    return day_rows,pair_rows,meta,arrays


def main():
    config=json.loads((ROOT/"source_manifest.json").read_text(encoding="utf-8"))
    inv=json.loads((ROOT/"data_inventory.json").read_text(encoding="utf-8"))
    compute=json.loads((ROOT/"output/compute_manifest.json").read_text(encoding="utf-8"))
    selected=[r for r in inv["records"] if r["merge_status"]!="quarantined_history"]
    if len(selected)!=compute["record_count"] or not compute["all_crc_validated"]:
        raise ValueError("Full content verification is incomplete for the selected inputs")
    records={};metrics=[];edges=[];main_peaks=[];feature_rows=[];feature_defs=[];pair_rows=[]
    for r in selected:
        rid=r["record_id"];file=ROOT/"output"/(rid+"_spectra.npz")
        q=json.loads((ROOT/"output"/(rid+"_quality.json")).read_text(encoding="utf-8"))
        if q['fft_length']!=config['processing']['fft_length'] or q['temporal_bins']!=config['processing']['temporal_bins']:
            raise ValueError('Requested processing parameters differ from cached FFT; recompute remotely')
        if q.get("input_crc32_expected")!=r["crc32_expected"] or q.get("input_file_bytes")!=r["file_size_bytes"]:
            raise ValueError("Cached spectrum/input mismatch: "+rid)
        if r["sample_rate_hz"]<r["acquisition_bandwidth_hz"]: raise ValueError("Declared RF bandwidth exceeds recorded complex sample coverage")
        x=dict(np.load(file));f=x["offset_hz"];power=x["mean_psd"];df=float(f[1]-f[0]);band=np.abs(f)<=r["acquisition_bandwidth_hz"]/2
        psd_db=db(power);floor=median_filter(psd_db,size=config["processing"]["feature_floor_bins"],mode="nearest");contrast=psd_db-floor
        peaks,_=find_peaks(contrast,height=6,prominence=3,distance=7)
        peaks=peaks[band[peaks]]
        current={"r":r,"q":q,"f":f,"df":df,"band":band,"psd":power,"psd_db":psd_db,"floor":floor,"contrast":contrast,"time_psd":x["time_psd"].astype(float),"time_centers_s":x["time_centers_s"],"peaks":peaks}
        records[rid]=current
        for rank,i in enumerate(sorted(peaks,key=lambda i:contrast[i],reverse=True),1):
            main_peaks.append({"record_id":rid,"experiment":r["experiment"],"file_name":r["file_name"],"rank":rank,"offset_hz":float(f[i]),"rf_hz_candidate_IQ":float(r["center_frequency_hz"]+f[i]),"rf_hz_candidate_QI":float(r["center_frequency_hz"]-f[i]),"local_floor_contrast_db":float(contrast[i]),"psd_db_digital_per_hz":float(psd_db[i]),"near_center_guard":bool(abs(f[i])<=5000),"near_band_edge_50khz":bool(abs(f[i])>r["acquisition_bandwidth_hz"]/2-50000),"source_attribution":"unresolved: no matched OFF/background recordings"})
        p=float(power[band].sum()*df);timep=current["time_psd"][:,band].sum(axis=1)*df
        hist=np.asarray(q.get("storage_histogram_8bit") or [],np.int64)
        if len(hist):
            prob=hist/hist.sum();nz=prob>0
            entropy=float(-np.sum(prob[nz]*np.log2(prob[nz])));cumsum=hist.cumsum()/hist.sum()
            occupied=int(np.count_nonzero(hist));mid=float(prob[128]);qlow=int(np.searchsorted(cumsum,.001));qhigh=int(np.searchsorted(cumsum,.999))
        else: entropy=mid=None;occupied=qlow=qhigh=None
        quality_flags=[]
        if mid is not None and mid>.9: quality_flags.append("more_than90pct_mid_code; low_code_occupancy")
        if p<=0 or not np.isfinite(p): quality_flags.append("zero_or_invalid_power")
        if q["pcm_endpoint_fraction"]>0: quality_flags.append("storage_endpoints_present; inspect clipping")
        r.update(full_zip_crc_validated=True,sha256_uncompressed_wav=q["sha256_uncompressed_wav"],quality_flags=";".join(quality_flags))
        row={"record_id":rid,"experiment":r["experiment"],"file_name":r["file_name"],"acquisition_date":r["acquisition_date"],"relative_day_confirmed":r["relative_day_confirmed"],"geometry":r["geometry"],"distance_label_cm":r["distance_label_cm"],"replicate":r["replicate"],"center_frequency_hz":r["center_frequency_hz"],"full_analyzed_bandwidth_hz":r["acquisition_bandwidth_hz"],"duration_s":r["duration_s"],"full_band_power_digital_unit2":p,"full_band_power_db":float(db(p)),"local_noise_floor_median_db_per_hz":float(np.median(floor[band])),"within_file_band_db_q10":float(np.quantile(db(timep),.1)),"within_file_band_db_q90":float(np.quantile(db(timep),.9)),"within_file_band_db_q90_minus_q10":float(np.ptp(np.quantile(db(timep),[.1,.9]))),"last_minus_first_temporal_band_db":float(db(timep[-1])-db(timep[0])),"storage_mid_code_fraction":mid,"occupied_storage_codes":occupied,"storage_code_entropy_bits_not_ENOB":entropy,"central_99_8pct_code_min":qlow,"central_99_8pct_code_max":qhigh,"storage_endpoint_fraction":q["pcm_endpoint_fraction"],"welch_segments":q["welch_segments"],"gain_fixed_confirmed":r["gain_fixed_confirmed"],"n_recordings":1,"independent_dates_confirmed":1 if r["acquisition_date"] else 0,"quality_flags":";".join(quality_flags)}
        current["metric"]=row;current["time_band_db"]=db(timep);metrics.append(row)
        for trim in [0,250000,500000,1000000,5000000]:
            mask=np.abs(f)<=r["acquisition_bandwidth_hz"]/2-trim
            ep=float(power[mask].sum()*df)
            edges.append({"record_id":rid,"experiment":r["experiment"],"trim_each_side_hz":trim,"included_bandwidth_hz":r["acquisition_bandwidth_hz"]-2*trim,"power_db":float(db(ep)),"fraction_of_full_band_power":ep/p,"analysis_role":"primary_full20MHz" if trim==0 else "legacy10MHz_diagnostic_only" if trim==5000000 else "edge_rolloff_sensitivity"})

    stable_ids=[r["record_id"] for r in selected if r["experiment"]=="stability"]
    stable_ids.sort(key=lambda rid:(records[rid]["r"].get("acquisition_date") or "9999",records[rid]["r"].get("filename_stability_suffix") or 0,rid))
    cable_ids=[r["record_id"] for r in selected if r["experiment"]=="cable"]
    main_cable_ids=sorted((rid for rid in cable_ids if records[rid]["r"]["primary_40_80_factorial"]),key=lambda rid:(records[rid]["r"]["distance_label_cm"],records[rid]["r"]["geometry"],records[rid]["r"]["replicate"]))
    # Enrollment uses a predeclared reference, not the best-scoring capture.
    stability_cohorts={records[rid]["r"]["longitudinal_cohort"] or records[rid]["r"]["source_id"] for rid in stable_ids}
    if len(stability_cohorts)>1:
        raise ValueError("Different stability cohorts cannot be pooled; review metadata or run each cohort separately")
    if any(records[rid]['r']['merge_status']=='approved_history' for rid in stable_ids):
        required=('acquisition_date','gain_db','agc','antenna_id','receiver_chain_id','receiver_power','recording_software','iq_order','device_state','longitudinal_cohort')
        if any(not records[rid]['r']['metadata_verified'] or any(records[rid]['r'].get(k) in (None,'') for k in required) for rid in stable_ids):
            raise ValueError('Before historical pooling, verify metadata for current as well as historical recordings')
        same_condition_fields=('device_id','device_state','gain_db','agc','antenna_id','receiver_chain_id','receiver_power','iq_order','center_frequency_hz','acquisition_bandwidth_hz','bits_per_sample','format_tag')
        differing=[k for k in same_condition_fields if len({str(records[rid]['r'].get(k)) for rid in stable_ids})>1]
        if differing: raise ValueError('Historical metadata differ; stratify into separate cohorts: '+','.join(differing))
    refs={"stability":stable_ids[0],"cable":next((rid for rid in main_cable_ids if records[rid]["r"]["geometry"]=="s" and records[rid]["r"]["distance_label_cm"]==40 and records[rid]["r"]["replicate"]==1),main_cable_ids[0])}
    banks={}
    for group,refid in refs.items():
        ref=records[refid];indices=[]
        for i in sorted(ref["peaks"],key=lambda i:ref["contrast"][i],reverse=True):
            if abs(ref["f"][i])<=5000 or abs(ref["f"][i])>=9_950_000: continue
            if all(abs(ref["f"][i]-ref["f"][j])>10000 for j in indices): indices.append(int(i))
            if len(indices)==8: break
        banks[group]=indices
        for j,i in enumerate(indices):
            feature_defs.append({"experiment":group,"feature_id":("TF" if group=="stability" else "WF")+f"{j+1:02d}","reference_record_id":refid,"reference_offset_hz":float(ref["f"][i]),"nominal_rf_hz_IQ":float(ref["r"]["center_frequency_hz"]+ref["f"][i]),"nominal_rf_hz_QI":float(ref["r"]["center_frequency_hz"]-ref["f"][i]),"selection":"top local contrast >=6dB from prespecified reference; minimum10kHz spacing; center/edge guards for features only","source_attribution":"not verified; stable ambient/receiver lines remain possible"})
        for rid in (stable_ids if group=="stability" else cable_ids):
            d=records[rid];mask=np.zeros(len(d["f"]),bool);found=0;contrasts=[];frow=[]
            for j,i in enumerate(indices):
                ref_f=ref["f"][i]
                same_mapping=d["r"]["center_frequency_hz"]==ref["r"]["center_frequency_hz"] and d["r"].get("iq_order")==ref["r"].get("iq_order")
                target_f=ref_f
                if not same_mapping:
                    ro=ref["r"].get("iq_order");do=d["r"].get("iq_order")
                    if ro not in ("I+jQ","Q+jI","I-jQ") or do not in ("I+jQ","Q+jI","I-jQ"):
                        raise ValueError("RF remapping requires confirmed recorder I/Q conventions")
                    rs=1 if ro=="I+jQ" else -1;ds=1 if do=="I+jQ" else -1
                    target_f=(ref["r"]["center_frequency_hz"]+rs*ref_f-d["r"]["center_frequency_hz"])/ds
                region=np.flatnonzero(np.abs(d["f"]-target_f)<=5000)
                if not len(region): continue
                candidates=d['peaks'][np.abs(d['f'][d['peaks']]-target_f)<=5000]
                k=int(candidates[np.argmax(d['psd'][candidates])]) if len(candidates) else int(region[np.argmax(d['psd'][region])])
                peakc=float(d["contrast"][k]);at_boundary=abs(d['f'][k]-target_f)>=5000-d['df']
                detected=bool(len(candidates) and peakc>=6 and not at_boundary)
                found+=int(detected);contrasts.append(peakc);mask[region]=True
                ti=region[np.argmax(d["time_psd"][:,region],axis=1)];tp=d["time_psd"][np.arange(len(ti)),ti]
                floor=np.array([np.median(db(d["time_psd"][t,max(0,k0-100):min(len(d["f"]),k0+101)])) for t,k0 in enumerate(ti)])
                tc=db(tp)-floor
                frow.append({"record_id":rid,"experiment":group,"file_name":d["r"]["file_name"],"geometry":d["r"]["geometry"],"distance_label_cm":d["r"]["distance_label_cm"],"replicate":d["r"]["replicate"],"acquisition_date":d["r"]["acquisition_date"],"feature_id":("TF" if group=="stability" else "WF")+f"{j+1:02d}","reference_record_id":refid,"reference_offset_hz":float(ref_f),"target_offset_hz_in_this_record":float(target_f),"searched_peak_offset_hz":float(d["f"][k]),"detected_above6db":detected,"frequency_shift_hz_if_detected":float(d["f"][k]-target_f) if detected else None,"frequency_shift_ppm_nominal_rf":float((d["f"][k]-target_f)/(ref["r"]["center_frequency_hz"]+ref_f)*1e6) if detected else None,"rf_hz_candidate_IQ":float(d["r"]["center_frequency_hz"]+d["f"][k]),"rf_hz_candidate_QI":float(d["r"]["center_frequency_hz"]-d["f"][k]),"peak_psd_db_per_hz":float(d["psd_db"][k]),"local_floor_contrast_db":peakc,"within_file_presence_fraction6db":float(np.mean(tc>=6)),"within_file_frequency_q10_hz":float(np.quantile(d["f"][ti],.1)),"within_file_frequency_q90_hz":float(np.quantile(d["f"][ti],.9)),"within_file_peak_psd_q10_db":float(np.quantile(db(tp),.1)),"within_file_peak_psd_q90_db":float(np.quantile(db(tp),.9))})
                frow[-1].update(search_window_boundary=bool(at_boundary),local_maximum_candidate=bool(len(candidates)),tracking_status='detected_candidate_source_unverified' if detected else 'not_reliably_detected_within5kHz; not evidence of physical absence')
            peak_top=max((f["peak_psd_db_per_hz"] for f in frow if f['detected_above6db']),default=0)
            for frowi in frow: frowi["relative_peak_amplitude_db"]=frowi["peak_psd_db_per_hz"]-peak_top if frowi['detected_above6db'] else None
            feature_rows.extend(frow)
            numerator=float(d["psd"][mask].sum()*d["df"])
            denominator=float((10**(d["floor"][mask]/10)).sum()*d["df"])
            d["metric"].update(template_reference=refid,template_candidate_count=len(indices),candidate_peaks_above6db=found,template_peak_presence_score=found/len(indices) if indices else None,fixed_peak_region_to_floor_db=float(db(numerator/denominator)) if denominator else None)
            x,y=aligned(ref,d,"psd_db");u,v=aligned(ref,d,"contrast")
            d["metric"].update(reference_log_psd_correlation=corr(x,y),reference_local_contrast_correlation=corr(u,v))

    extra_ids=[rid for rid in cable_ids if rid not in main_cable_ids]
    for group,ids in (("stability",stable_ids),("cable_main",main_cable_ids),("cable_extra",extra_ids)):
        for a,b in combinations(ids,2):
            if group=='cable_extra' and (records[a]['r']['geometry'],records[a]['r']['distance_label_cm'])!=(records[b]['r']['geometry'],records[b]['r']['distance_label_cm']): continue
            x,y=aligned(records[a],records[b],"psd_db");u,v=aligned(records[a],records[b],"contrast")
            ra,rb=records[a]["r"],records[b]["r"]
            same_cond=ra["geometry"]==rb["geometry"] and ra["distance_label_cm"]==rb["distance_label_cm"] if group.startswith('cable') else None
            pair_rows.append({"group":group,"record_a":a,"record_b":b,"log_psd_correlation":corr(x,y),"local_contrast_correlation":corr(u,v),"same_wire_condition":same_cond,"calendar_date_a":ra["acquisition_date"],"calendar_date_b":rb["acquisition_date"],"verified_cross_date":bool(ra["acquisition_date"] and rb["acquisition_date"] and ra["acquisition_date"]!=rb["acquisition_date"]),"pair_is_independent_replicate":False})
    condition_ids=defaultdict(list)
    for rid in cable_ids:
        r=records[rid]["r"];condition_ids[(r["geometry"],r["distance_label_cm"])].append(rid)
    condition_rows=[]
    for (geometry,distance),ids in sorted(condition_ids.items()):
        group_metrics=[records[rid]["metric"] for rid in ids]
        powers=[v["full_band_power_db"] for v in group_metrics];ratio=[v["fixed_peak_region_to_floor_db"] for v in group_metrics]
        within=[p["local_contrast_correlation"] for p in pair_rows if p["group"].startswith('cable') and p["record_a"] in ids and p["record_b"] in ids]
        condition_rows.append({"geometry":geometry,"distance_label_cm":distance,"technical_replicates":len(ids),"independent_dates_verified":len({records[rid]["r"]["acquisition_date"] for rid in ids if records[rid]["r"]["acquisition_date"]}),"full_band_log_power_mean_db":np.mean(powers),"full_band_log_power_sd_db":np.std(powers,ddof=1) if len(ids)>1 else None,"full_band_log_power_min_db":min(powers),"full_band_log_power_max_db":max(powers),"power_linear_mean":np.mean([v["full_band_power_digital_unit2"] for v in group_metrics]),"peak_to_floor_mean_db":np.mean(ratio) if all(v is not None for v in ratio) else None,"peak_to_floor_sd_db":np.std(ratio,ddof=1) if len(ids)>1 and all(v is not None for v in ratio) else None,"template_presence_score_mean":np.mean([v["template_peak_presence_score"] for v in group_metrics]) if banks["cable"] else None,"within_condition_local_corr_mean":np.mean(within) if within else None,"within_condition_local_corr_min":min(within) if within else None,"record_ids":";".join(ids),"repeat_unit":"four consecutive technical recordings, not four independent dates"})
    contrasts=[]
    def factorial(values,metric,role):
        c40=np.mean(values[("c",40)]);s40=np.mean(values[("s",40)]);c80=np.mean(values[("c",80)]);s80=np.mean(values[("s",80)])
        return [{"metric":metric,"comparison":name,"difference":float(v),"role":role,"inference":"descriptive technical-repeat contrast; gain/time/geometry metadata unresolved; no p-value"} for name,v in (("c40_minus_s40",c40-s40),("c80_minus_s80",c80-s80),("c80_minus_c40",c80-c40),("s80_minus_s40",s80-s40),("interaction_(c80-s80)-(c40-s40)",(c80-s80)-(c40-s40)))]
    for field in ("full_band_power_db","fixed_peak_region_to_floor_db"):
        values={key:[records[rid]["metric"][field] for rid in ids] for key,ids in condition_ids.items() if key[1] in (40,80)}
        if all(all(v is not None for v in vv) for vv in values.values()): contrasts+=factorial(values,field,"primary20MHz")
    edge_contrasts=[]
    for trim in (0,250000,500000,1000000,5000000):
        values=defaultdict(list)
        for e in edges:
            rr=records[e["record_id"]]["r"]
            if rr["primary_40_80_factorial"] and e["trim_each_side_hz"]==trim: values[(rr["geometry"],rr["distance_label_cm"])].append(e["power_db"])
        for v in factorial(values,"log_band_power_db","full20MHz" if trim==0 else "edge_sensitivity" if trim<5000000 else "legacy10MHz_diagnostic"):
            v.update(trim_each_side_hz=trim,included_bandwidth_hz=20000000-2*trim);edge_contrasts.append(v)
    # Confirmed daily analyses are generated only if actual dates have been supplied.
    date_groups=defaultdict(list)
    for rid in stable_ids:
        r=records[rid]["r"]
        if r["acquisition_date"]: date_groups[(r["longitudinal_cohort"] or r["source_id"],r["acquisition_date"])].append(rid)
    day_rows=[]
    for (cohort,date),ids in sorted(date_groups.items()):
        row={"cohort":cohort,"acquisition_date":date,"recordings":len(ids),"mean_log_power_db":np.mean([records[rid]["metric"]["full_band_power_db"] for rid in ids]),"mean_reference_local_contrast_correlation":np.mean([records[rid]["metric"]["reference_local_contrast_correlation"] for rid in ids]),"gain_comparability_confirmed":all(records[rid]["r"]["gain_fixed_confirmed"] for rid in ids)}
        day_rows.append(row)
    verified_dates=sorted({r["acquisition_date"] for r in selected if r["experiment"]=="stability" and r["acquisition_date"]})
    if verified_dates:
        calendar_days=[calendar_date.fromisoformat(v) for v in verified_dates]
        full_dates=[calendar_days[0]+timedelta(days=i) for i in range((calendar_days[-1]-calendar_days[0]).days+1)]
        missing_dates=[v.isoformat() for v in full_dates if v not in calendar_days]
    else: missing_dates=[]
    temporal_pairs=[p for p in pair_rows if p["group"]=="stability"]
    duplicate_hash=defaultdict(list)
    for r in selected: duplicate_hash[r["sha256_uncompressed_wav"]].append(r["record_id"])
    duplicates=[v for v in duplicate_hash.values() if len(v)>1]
    result={"analysis_id":config["analysis_id"],"counts":dict(Counter(r["experiment"] for r in selected)),"acquisition_bandwidth_hz":20000000,"frequency_bands":{"stability_hz":[1577000000,1597000000],"cable_hz":[10000000,30000000]},"methods":{"FFT":65536,"window":"periodicHann","overlap":.5,"grid_hz":20000000/65536,"ENBW_hz":1.5*20000000/65536,"primary_power_mask":"all20MHz FFT bins including center; per-segment mean removal in Welch","PCM8_scale":"(u8-128)/128","feature_only_center_guard_hz":5000,"feature_floor_bins":201,"feature_track_half_width_hz":5000,"no_cross_experiment_correlations":True,"gain_calibration":"unknown; digital power only"},"stability":{"record_ids":stable_ids,"reference_record_id":refs["stability"],"confirmed_calendar_dates":verified_dates,"confirmed_date_count":len(verified_dates),"ten_day_coverage_verified":len(verified_dates)>=10 and not missing_dates,"missing_calendar_dates_within_span":missing_dates,"cross_day_claim_status":"not established without dates and compatible acquisition conditions" if len(verified_dates)<2 else "descriptive cross-date results; check cohort/settings before longitudinal claims","log_psd_pair_correlation":summarize([p["log_psd_correlation"] for p in temporal_pairs]),"local_contrast_pair_correlation":summarize([p["local_contrast_correlation"] for p in temporal_pairs]),"power_db":summarize([records[rid]["metric"]["full_band_power_db"] for rid in stable_ids]),"candidate_feature_count":len(banks["stability"]),"template_presence_scores":[records[rid]["metric"]["template_peak_presence_score"] for rid in stable_ids],"single_class_only":True,"classification_accuracy_and_macro_f1":None,"reason":"Only heater2 positive records; no negative/other-device test set, and dates unresolved"},"cable":{"reference_record_id":refs["cable"],"main_record_ids":main_cable_ids,"condition_statistics":condition_rows,"factorial_contrasts":contrasts,"edge_sensitivity_contrasts":edge_contrasts,"candidate_feature_count":len(banks["cable"]),"technical_replicates_per_condition":4,"distance_object":"unconfirmed","label_correction":"originals150cm-4 is s160cm repeat4 per user; raw name unchanged","source_attribution":"unverified; no matchedOFF/background or pathway intervention"},"metrics":metrics,"feature_definitions":feature_defs,"content_duplicates":duplicates,"raw_crc_all_passed":compute["all_crc_validated"],"max_reference_welch_relative_error":compute["max_reference_welch_relative_error"],"compute_wall_seconds":compute["wall_seconds"],"compute_versions":compute["versions"],"unresolved":["actual dates/meaning of10day suffix","gain/AGC","I/Q order and recorder software","antenna/receiver power configuration","distance measurement object","matchedOFF/background","source of fixed narrow peaks"],"history_quarantine_count":sum(r["merge_status"]=="quarantined_history" for r in inv["records"])}
    for file,rows in (("record_metrics.csv",metrics),("main_peaks.csv",main_peaks),("feature_definitions.csv",feature_defs),("feature_tracking.csv",feature_rows),("pairwise_similarity.csv",pair_rows),("cable_condition_statistics.csv",condition_rows),("cable_factorial_contrasts.csv",contrasts),("edge_sensitivity_record.csv",edges),("edge_sensitivity_contrasts.csv",edge_contrasts)):
        table_write(ROOT/file,[finite_json(v) for v in rows])
    table_write(ROOT/"verified_daily_statistics.csv",day_rows,["cohort","acquisition_date","recordings","mean_log_power_db","mean_reference_local_contrast_correlation","gain_comparability_confirmed"])
    daily_rows,daily_pairs,daily_meta,daily_arrays=daily_analysis(records,stable_ids,config.get('stability_enrollment_date'))
    table_write(ROOT/'verified_day1_template_scores.csv',daily_rows,['acquisition_date','recordings','reference_date','reference_is_confirmed_experiment_day1','day1_date','daily_mean_template_log_psd_corr','daily_mean_template_local_corr','reference_candidate_count','reference_peak_presence_score','day1_mean_candidate_count','day1_mean_peak_presence_score','within_day_independent_record_pair_count','interpretation'])
    table_write(ROOT/'verified_daily_pairwise_similarity.csv',daily_pairs,['date_a','date_b','log_psd_correlation','local_contrast_correlation'])
    result['stability']['daily_analysis']=daily_meta
    grids=sorted({records[rid]['df'] for rid in records})
    result['methods'].update(grid_hz=grids[0] if len(grids)==1 else grids,
                             ENBW_hz=1.5*grids[0] if len(grids)==1 else [1.5*g for g in grids],
                             frequency_grid_hz_by_record={rid:records[rid]['df'] for rid in records})
    arrays={}
    for rid,d in records.items():
        for key in ("f","psd","psd_db","floor","contrast","time_band_db"):
            arrays[rid+"__"+key]=d[key]
    arrays.update(daily_arrays)
    np.savez_compressed(ROOT/"derived_spectra.npz",**arrays)
    (ROOT/"analysis_summary.json").write_text(json.dumps(finite_json(result),ensure_ascii=False,indent=2),encoding="utf-8")
    (ROOT/"data_inventory.json").write_text(json.dumps(finite_json(inv),ensure_ascii=False,indent=2),encoding="utf-8")
    table_write(ROOT/"data_index.csv",[{k:v for k,v in r.items() if k!="header_details"} for r in inv["records"]])
    print(json.dumps(finite_json({"counts":result["counts"],"stability":result["stability"],"cable_contrasts":contrasts,"conditions":condition_rows,"duplicates":duplicates}),ensure_ascii=False,indent=2))


if __name__=="__main__": main()
