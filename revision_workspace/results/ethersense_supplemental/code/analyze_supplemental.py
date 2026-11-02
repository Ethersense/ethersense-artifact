"""Lightweight, transparent statistics over remotely computed measured spectra."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks
from scipy.stats import spearmanr

PEAK_THRESHOLD_DB = 6.0
FLOOR_BINS = 201
DC_GUARD_HZ = 5000.0
TRACK_HALF_WIDTH_HZ = 5000.0
TOP_TEMPLATE_PEAKS = 8


def db(x):
    return 10*np.log10(np.maximum(x, np.finfo(float).tiny))


def csv_write(path, rows):
    if not rows:
        return
    fields = list(rows[0])
    fields += sorted({k for r in rows for k in r}-set(fields))
    with Path(path).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def seconds(t):
    h,m,s=map(int,t.split(":"))
    return h*3600+m*60+s


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",default="results/ethersense_supplemental")
    a=p.parse_args()
    root=Path(a.root)
    inventory=json.loads((root/"data_inventory.json").read_text(encoding="utf-8"))
    confirmations=json.loads((root/"conditions_confirmation.json").read_text(encoding="utf-8"))
    manifest=json.loads((root/"output/compute_manifest.json").read_text(encoding="utf-8"))
    if manifest["record_count"] != len(inventory["records"]) or not manifest["all_crc_validated"]:
        raise ValueError("Cannot report complete results before full raw-data verification")
    groups={"导线实验":"A","导线实验2（沿着导线1-10m）":"B","并联实验":"C"}
    records={}
    for r in inventory["records"]:
        rid=f'{groups[r["experiment_folder"]]}{r["chronological_index"]:02d}'
        r["record_id"]=rid
        quality=json.loads((root/"output"/(rid+"_quality.json")).read_text(encoding="utf-8"))
        r["full_zip_crc_validated"]=quality["full_zip_crc_validated"]
        r["sha256_uncompressed_wav"]=quality["sha256_uncompressed_wav"]
        if confirmations.get("acquisition_date"):
            r["measurement_date"]=confirmations["acquisition_date"]
            r["date_status"]="user-confirmed"
        r["gain_comparability"]="user-confirmed fixed gain" if confirmations.get("gain_fixed_all_files") else "unconfirmed; digital power comparisons conditional"
        records[rid]={"record":r,"quality":quality,**dict(np.load(root/"output"/(rid+"_spectra.npz")))}
    freq=records["A01"]["offset_hz"]
    step=freq[1]-freq[0]
    band=(np.abs(freq)<=5_000_000)&(np.abs(freq)>DC_GUARD_HZ)
    valid_peaks=band&(np.abs(freq)<4_950_000)
    all_peak_rows=[]
    for rid,d in records.items():
        pdb=db(d["mean_psd"])
        floor=median_filter(pdb,size=FLOOR_BINS,mode="nearest")
        contrast=pdb-floor
        peaks,props=find_peaks(contrast,height=PEAK_THRESHOLD_DB,prominence=3.0,distance=7)
        peaks=peaks[valid_peaks[peaks]]
        d.update(psd_db=pdb,floor_db=floor,contrast_db=contrast,peak_indices=peaks)
        base=records["C04"] if rid.startswith("C") else records["A09"]
        d["base_id"]="C04" if rid.startswith("C") else "A09"
    for rid,d in records.items():
        base=records[d["base_id"]]
        for rank,i in enumerate(sorted(d["peak_indices"],key=lambda i:d["contrast_db"][i],reverse=True),1):
            fc=d["record"]["center_frequency_hz"]
            base_region=slice(i-3,i+4)
            bg=float(base["contrast_db"][base_region].max())
            row={"record_id":rid,"file_name":d["record"]["file_name"],"rank_by_local_contrast":rank,"offset_hz_ch1_plus_j_ch2":float(freq[i]),"rf_hz_candidate_IQ":float(fc+freq[i]),"rf_hz_candidate_QI":float(fc-freq[i]),"absolute_frequency_confirmed":confirmations.get("iq_channel_1_is_i_channel_2_is_q") is not None,"psd_db_digital_per_hz":float(d["psd_db"][i]),"local_floor_contrast_db":float(d["contrast_db"][i]),"base_local_contrast_db_near_frequency":bg,"contrast_increase_over_background_db":float(d["contrast_db"][i]-bg),"candidate_related_to_changed_condition":bool(d["contrast_db"][i]-bg>=PEAK_THRESHOLD_DB),"caution":"one recording/condition; gain, time, receiver artifacts and source identity unresolved"}
            all_peak_rows.append(row)
    csv_write(root/"main_peaks.csv",all_peak_rows)

    def select_template(rid,n=TOP_TEMPLATE_PEAKS):
        d=records[rid]
        bg=records[d["base_id"]]
        candidates=sorted(d["peak_indices"],key=lambda i:d["contrast_db"][i],reverse=True)
        selected=[]
        for i in candidates:
            base_prom=bg["contrast_db"][i-3:i+4].max()
            if d["contrast_db"][i]-base_prom >= PEAK_THRESHOLD_DB and all(abs(freq[i]-freq[j])>2*TRACK_HALF_WIDTH_HZ for j in selected):
                selected.append(int(i))
            if len(selected)==n:
                break
        return selected

    templates={"A":select_template("A04"),"B":select_template("B01")}
    c_union=[]
    for cid in ("C01","C03"):
        for i in select_template(cid):
            if all(abs(freq[i]-freq[j])>2*TRACK_HALF_WIDTH_HZ for j in c_union):
                c_union.append(i)
    strict_c_candidates=c_union.copy()
    # When no condition-enhanced line clears the rule, still compare measured
    # common/background lines. This must never be presented as source isolation.
    c_selection="condition-enhanced candidates"
    if not c_union:
        c_selection="representative common/background peaks; no source attribution"
        strongest=sorted(((float(records[rid]["contrast_db"][i]),int(i)) for rid in ("C01","C03","C04") for i in records[rid]["peak_indices"]),reverse=True)
        for level,i in strongest:
            if all(abs(freq[i]-freq[j])>2*TRACK_HALF_WIDTH_HZ for j in c_union):
                c_union.append(i)
            if len(c_union)==TOP_TEMPLATE_PEAKS:
                break
    templates["C"]=c_union
    features=[]
    template_description=[]
    half=int(np.ceil(TRACK_HALF_WIDTH_HZ/step))
    for group,indices in templates.items():
        ids=sorted(rid for rid in records if rid.startswith(group))
        if group=="B":
            ids.append("A09")
        template_mask=np.zeros(freq.shape,dtype=bool)
        for j,i in enumerate(indices):
            template_mask[i-half:i+half+1]=True
            ref="A04" if group=="A" else "B01" if group=="B" else "C01/C03"
            fc=20_000_000 if group in ("A","B") else 19_600_000
            template_description.append({"experiment":group,"feature_id":f"{group}F{j+1:02d}","reference":ref,"reference_offset_hz":float(freq[i]),"rf_hz_candidate_IQ":float(fc+freq[i]),"rf_hz_candidate_QI":float(fc-freq[i]),"track_half_width_hz":TRACK_HALF_WIDTH_HZ,"selection":c_selection if group=="C" else "local contrast >=6 dB and >=6 dB above background contrast; first reference only"})
        for rid in ids:
            d=records[rid]
            time_p=d["time_psd"].astype(float)
            peak_vectors=[]
            for j,i in enumerate(indices):
                region=np.arange(i-half,i+half+1)
                i_obs=int(region[np.argmax(d["mean_psd"][region])])
                temporal_peak_i=region[np.argmax(time_p[:,region],axis=1)]
                t_psd=time_p[np.arange(len(time_p)),temporal_peak_i]
                t_floor=np.array([np.median(db(time_p[t,k-FLOOR_BINS//2:k+FLOOR_BINS//2+1])) for t,k in enumerate(temporal_peak_i)])
                temporal_contrast=db(t_psd)-t_floor
                background=records[d["base_id"]]
                bgmax=float(background["contrast_db"][region].max())
                observed_contrast=float(d["contrast_db"][i_obs])
                peak_vectors.append(observed_contrast)
                features.append({"template_experiment":group,"record_id":rid,"file_name":d["record"]["file_name"],"distance_m":d["record"]["distance_m"],"condition":d["record"]["condition"],"feature_id":f"{group}F{j+1:02d}","reference_offset_hz":float(freq[i]),"observed_offset_hz":float(freq[i_obs]),"rf_hz_candidate_IQ":float(d["record"]["center_frequency_hz"]+freq[i_obs]),"rf_hz_candidate_QI":float(d["record"]["center_frequency_hz"]-freq[i_obs]),"frequency_shift_from_reference_hz":float(freq[i_obs]-freq[i]),"peak_psd_db_digital_per_hz":float(d["psd_db"][i_obs]),"local_floor_contrast_db":observed_contrast,"background_contrast_db_near_frequency":bgmax,"contrast_increase_over_background_db":observed_contrast-bgmax,"feature_retained_at_6db_rule":bool(observed_contrast>=PEAK_THRESHOLD_DB and observed_contrast-bgmax>=PEAK_THRESHOLD_DB),"within_file_presence_fraction_6db":float(np.mean(temporal_contrast>=PEAK_THRESHOLD_DB)),"within_file_peak_psd_q10_db":float(np.quantile(db(t_psd),.1)),"within_file_peak_psd_q90_db":float(np.quantile(db(t_psd),.9)),"within_file_peak_frequency_q10_hz":float(np.quantile(freq[temporal_peak_i],.1)),"within_file_peak_frequency_q90_hz":float(np.quantile(freq[temporal_peak_i],.9)),"independent_replicates":1})
            if rid.startswith(group):
                d["template_mask"]=template_mask
                d["template_peak_contrasts"]=peak_vectors
                d["feature_count_retained"]=sum(f["feature_retained_at_6db_rule"] for f in features if f["record_id"]==rid and f["template_experiment"]==group)
                sig=float(d["mean_psd"][template_mask].sum()*step)
                noise=float((10**(d["floor_db"][template_mask]/10)).sum()*step)
                d["template_power"]=sig
                d["template_pbr_db"]=float(db(sig/noise)) if noise else None
    csv_write(root/"feature_definitions.csv",template_description)
    csv_write(root/"feature_tracking.csv",features)

    metrics=[]
    for rid,d in records.items():
        integrated=float(d["mean_psd"][band].sum()*step)
        time_power=d["time_psd"][:,band].sum(axis=1,dtype=np.float64)*step
        time_db=db(time_power)
        full_power=float(d["mean_psd"][np.abs(freq)>DC_GUARD_HZ].sum()*step)
        row={"record_id":rid,"experiment":rid[0],"file_name":d["record"]["file_name"],"condition":d["record"]["condition"],"distance_m":d["record"]["distance_m"],"filename_time":d["record"]["filename_time"],"duration_s":d["record"]["duration_s"],"passband_power_digital_unit2":integrated,"passband_power_db_digital_unit2":float(db(integrated)),"full_sampled_band_power_digital_unit2":full_power,"analyzed_10mhz_fraction_of_sampled_spectrum":integrated/full_power,"passband_psd_median_db_per_hz":float(np.median(d["psd_db"][band])),"feature_band_power_digital_unit2":d.get("template_power"),"feature_band_power_db_digital_unit2":float(db(d["template_power"])) if d.get("template_power",0)>0 else None,"feature_band_to_local_floor_ratio_db":d.get("template_pbr_db"),"feature_template_count":len(templates[rid[0]]),"features_retained_6db":d.get("feature_count_retained",0),"within_file_band_power_q10_db":float(np.quantile(time_db,.1)),"within_file_band_power_q90_db":float(np.quantile(time_db,.9)),"within_file_band_power_q90_minus_q10_db":float(np.quantile(time_db,.9)-np.quantile(time_db,.1)),"last_vs_first_temporal_bin_db":float(time_db[-1]-time_db[0]),"pcm_endpoint_fraction":d["quality"]["pcm_endpoint_fraction"],"max_absolute_pcm":d["quality"]["maximum_absolute_pcm"],"welch_segments":d["quality"]["welch_segments"],"gain_fixed_confirmed":bool(confirmations.get("gain_fixed_all_files")),"independent_replicates":1}
        d["metrics"]=row
        metrics.append(row)
    csv_write(root/"quantitative_metrics.csv",metrics)
    subbands=[]
    for rid,d in records.items():
        for left,right in ((-5,-3),(-3,-1),(-1,1),(1,3),(3,5)):
            mask=band&(freq>=left*1e6)&(freq<right*1e6)
            power=float(d["mean_psd"][mask].sum()*step)
            subbands.append({"record_id":rid,"offset_band_mhz":f"{left} to {right}","offset_min_hz":left*1e6,"offset_max_hz":right*1e6,"digital_power_unit2":power,"digital_power_db":float(db(power)),"fraction_of_analyzed_band_power":power/d["metrics"]["passband_power_digital_unit2"],"frequency_orientation_confirmed":confirmations.get("iq_channel_1_is_i_channel_2_is_q") is not None})
    csv_write(root/"subband_power.csv",subbands)
    pairs=[]
    for distance in range(1,5):
        positive=next(d for rid,d in records.items() if rid.startswith("A") and d["record"]["distance_m"]==distance)
        negative=next(d for rid,d in records.items() if rid.startswith("A") and d["record"]["distance_m"]==-distance)
        pwrp=positive["metrics"]["passband_power_db_digital_unit2"]
        pwrn=negative["metrics"]["passband_power_db_digital_unit2"]
        pairs.append({"absolute_distance_m":distance,"positive_record_id":positive["record"]["record_id"],"negative_record_id":negative["record"]["record_id"],"measurement_time_gap_s":seconds(negative["record"]["filename_time"])-seconds(positive["record"]["filename_time"]),"positive_band_power_db":pwrp,"negative_band_power_db":pwrn,"positive_minus_negative_band_power_db":pwrp-pwrn,"positive_minus_negative_feature_power_db":positive["metrics"]["feature_band_power_db_digital_unit2"]-negative["metrics"]["feature_band_power_db_digital_unit2"] if templates["A"] else None,"positive_minus_negative_template_floor_ratio_db":positive["template_pbr_db"]-negative["template_pbr_db"] if templates["A"] else None,"caution":"direction/time confounded; gains not confirmed; one recording per point"})
    csv_write(root/"A_direction_pairs.csv",pairs)
    bm=[records[f"B{i:02d}"]["metrics"] for i in range(1,11)]
    bpower=np.array([r["passband_power_db_digital_unit2"] for r in bm])
    bpbr=np.array([r["feature_band_to_local_floor_ratio_db"] for r in bm],float)
    sensitivity=[]
    for floor_bins in (101,201,401):
        temp_floor={rid:median_filter(records[rid]["psd_db"],size=floor_bins,mode="nearest") for rid in ["A09","B01","B10"]}
        for threshold in (3.0,6.0,10.0):
            for rid in ("B01","B10"):
                count=0
                for i in templates["B"]:
                    region=np.arange(i-half,i+half+1)
                    peak=int(region[np.argmax(records[rid]["mean_psd"][region])])
                    level=records[rid]["psd_db"][peak]-temp_floor[rid][peak]
                    bg=(records["A09"]["psd_db"]-temp_floor["A09"])[region].max()
                    count+=int(level>=threshold and level-bg>=threshold)
                sensitivity.append({"record_id":rid,"floor_median_bins":floor_bins,"floor_median_span_hz":floor_bins*step,"threshold_db":threshold,"retained_of_fixed_1m_template":count,"template_size":len(templates["B"]),"caution":"sensitivity of same selected template; no held-out device detection validation"})
    csv_write(root/"B_threshold_sensitivity.csv",sensitivity)
    c_sensitivity=[]
    for threshold in (3.0,6.0,10.0):
        for rid in ("C01","C03"):
            d=records[rid]
            found,_=find_peaks(d["contrast_db"],height=threshold,prominence=3.0,distance=7)
            selected=[int(i) for i in found if valid_peaks[i] and d["contrast_db"][i]-records["C04"]["contrast_db"][i-3:i+4].max()>=threshold]
            c_sensitivity.append({"record_id":rid,"threshold_db":threshold,"condition_enhanced_peak_count":len(selected),"offset_hz_list":";".join(str(float(freq[i])) for i in selected),"caution":"condition association candidates, not confirmed device contributions"})
    csv_write(root/"C_threshold_sensitivity.csv",c_sensitivity)
    c1,c2,c3,c4=[records[f"C{i:02d}"] for i in range(1,5)]
    prediction=c1["mean_psd"]+c3["mean_psd"]-c4["mean_psd"]
    residual=c2["mean_psd"]-prediction
    predicted_integral=float(prediction[band].sum()*step)
    observed_integral=c2["metrics"]["passband_power_digital_unit2"]
    c_peaks=[]
    for j,i in enumerate(templates["C"]):
        fid=f"CF{j+1:02d}"
        selected={f["record_id"]:f for f in features if f["template_experiment"]=="C" and f["feature_id"]==fid}
        u=selected["C01"]["contrast_increase_over_background_db"]
        v=selected["C03"]["contrast_increase_over_background_db"]
        attribution="两种单设备标签条件均增强" if u>=6 and v>=6 else "电瓶车断开标签条件增强" if u>=6 else "电器2断开标签条件增强" if v>=6 else "弱峰/背景共有"
        c_peaks.append({"feature_id":fid,"offset_hz":float(freq[i]),"rf_hz_candidate_IQ":float(19_600_000+freq[i]),"rf_hz_candidate_QI":float(19_600_000-freq[i]),"C01_local_contrast_db":selected["C01"]["local_floor_contrast_db"],"C02_local_contrast_db":selected["C02"]["local_floor_contrast_db"],"C03_local_contrast_db":selected["C03"]["local_floor_contrast_db"],"C04_local_contrast_db":selected["C04"]["local_floor_contrast_db"],"C01_vs_C04_contrast_change_db":u,"C03_vs_C04_contrast_change_db":v,"observed_condition_association":attribution,"device_assignment_confirmed":bool(confirmations.get("device2_is_heater") and confirmations.get("other_device_remained_on_when_one_disconnected")),"joint_keeps_feature_at_6db":selected["C02"]["feature_retained_at_6db_rule"]})
    csv_write(root/"C_condition_peak_association.csv",c_peaks)
    np.savez_compressed(root/"derived_spectra.npz",offset_hz=freq,**{f"{rid}_psd":d["mean_psd"] for rid,d in records.items()},**{f"{rid}_contrast":d["contrast_db"] for rid,d in records.items()},**{f"{rid}_time_power_db":db(d["time_psd"][:,band].sum(axis=1,dtype=np.float64)*step) for rid,d in records.items()},C_additive_prediction=prediction,C_additive_residual=residual)
    # The two I/Q conventions must be aligned to RF separately. Never align
    # different center-frequency recordings simply by FFT array position.
    axis_sensitivity=[]
    grid=np.arange(15_050_000,24_550_001,5_000.0)
    for sign in (1,-1):
        def on_rf(rid):
            d=records[rid]
            rf=d["record"]["center_frequency_hz"]+sign*freq
            sort=np.argsort(rf)
            return np.interp(grid,rf[sort],d["contrast_db"][sort])
        for other in ("C01","C03","C04"):
            x=on_rf("B01")
            y=on_rf(other)
            valid=(np.abs(grid-20_000_000)>DC_GUARD_HZ)&(np.abs(grid-19_600_000)>DC_GUARD_HZ)
            rho=float(spearmanr(x[valid],y[valid]).statistic)
            axis_sensitivity.append({"rf_mapping":"fc+offset" if sign==1 else "fc-offset","reference":"B01","comparison":other,"common_RF_band_hz":"15050000-24550000","spearman_local_contrast_rf_aligned":rho,"axis_confirmation":"unconfirmed; correlations cannot certify recorder I/Q order"})
    csv_write(root/"frequency_axis_sensitivity.csv",axis_sensitivity)
    summary={"analysis_status":"completed descriptive analysis with explicitly unresolved hardware/state metadata","conditions_confirmation":confirmations,"data_counts":inventory["group_counts"],"parameters":{"fft_length":65536,"frequency_bin_hz":float(step),"hann_enbw_hz":float(1.5*step),"rf_bandwidth_user_report_hz":10_000_000,"analyzed_offset_range_hz":[-5_000_000,5_000_000],"excluded_center_guard_hz":DC_GUARD_HZ,"noise_floor_median_bins":FLOOR_BINS,"noise_floor_span_hz":float(FLOOR_BINS*step),"peak_local_contrast_threshold_db":PEAK_THRESHOLD_DB,"template_track_half_width_hz":TRACK_HALF_WIDTH_HZ,"template_count":{g:len(v) for g,v in templates.items()},"amplitude_unit":"PCM16 / 32768; power relative to 1 normalized digital unit squared","frequency_orientation":"ch1+j ch2 offset; RF fc+offset and fc-offset are both retained until confirmed","uncertainty":"10th-90th percentiles over 16 temporal bins within a single recording; not confidence intervals or independent replicates"},"A_pairs":pairs,"B":{"band_power_db_1_to_10m":bpower.tolist(),"template_floor_ratio_db_1_to_10m":bpbr.tolist(),"band_power_10m_minus_1m_db":float(bpower[-1]-bpower[0]),"band_power_spearman_distance":float(spearmanr(np.arange(1,11),bpower).statistic),"band_power_adjacent_increases":[{"from_m":i+1,"to_m":i+2,"change_db":float(delta)} for i,delta in enumerate(np.diff(bpower)) if delta>0],"template_floor_ratio_spearman_distance":float(spearmanr(np.arange(1,11),bpbr).statistic) if np.isfinite(bpbr).all() else None,"far_10m_features_retained":bm[-1]["features_retained_6db"],"template_size":len(templates["B"]),"threshold_sensitivity":sensitivity},"C":{"device_assignment_pending":not bool(confirmations.get("device2_is_heater") and confirmations.get("other_device_remained_on_when_one_disconnected")),"additive_formula":"P_pred=P_C01+P_C03-P_C04, conditional on confirmed solo labels, fixed gain/geometry, background stationarity and uncorrelated emissions","gain_comparability_confirmed":bool(confirmations.get("gain_fixed_all_files")),"predicted_band_power_digital_unit2":predicted_integral,"observed_joint_band_power_digital_unit2":observed_integral,"observed_vs_predicted_band_db":float(db(observed_integral/predicted_integral)) if predicted_integral>0 else None,"condition_enhanced_candidate_count":len(strict_c_candidates),"threshold_sensitivity":c_sensitivity,"comparison_peak_selection":c_selection,"full_sampled_band_conditional_additivity_ratio_db":float(db(c2["metrics"]["full_sampled_band_power_digital_unit2"]/(c1["metrics"]["full_sampled_band_power_digital_unit2"]+c3["metrics"]["full_sampled_band_power_digital_unit2"]-c4["metrics"]["full_sampled_band_power_digital_unit2"]))),"negative_predicted_psd_fraction":float(np.mean(prediction[band]<=0)),"signed_residual_band_integral":float(residual[band].sum()*step),"peak_association":c_peaks},"frequency_axis_sensitivity":axis_sensitivity,"metrics":metrics,"compute_manifest":{"all_crc_validated":manifest["all_crc_validated"],"max_reference_welch_relative_error":manifest["max_reference_welch_relative_error"],"wall_seconds":manifest["wall_seconds"],"versions":manifest["versions"]},"source_paper":"project-local LaTeX source (2026-10-02 revision)","reused_code":"Existing figure notebook style only; no empirical WAV pipeline found in located project files."}
    (root/"analysis_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    inventory["records"]=[d["record"] for d in records.values()]
    (root/"data_inventory.json").write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding="utf-8")
    csv_write(root/"data_index.csv",[{k:v for k,v in d["record"].items() if k!="header_details"} for d in records.values()])
    print(json.dumps({"templates":summary["parameters"]["template_count"],"A_pairs":pairs,"B":{k:v for k,v in summary["B"].items() if k!="threshold_sensitivity"},"C":{k:v for k,v in summary["C"].items() if k!="peak_association"}},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
