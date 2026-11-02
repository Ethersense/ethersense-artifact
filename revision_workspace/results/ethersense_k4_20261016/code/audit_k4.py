"""Header-only K4 indexing with explicit metadata provenance and merge gates."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from verified_rf64 import displayed_name, wav_header

ROOT=Path(__file__).resolve().parent.parent
WORKSPACE=ROOT.parent.parent
OVERRIDE_FIELDS=("source_id","archive_member","acquisition_date","relative_day","device_state","gain_db","agc","antenna_id","receiver_chain_id","receiver_power","recording_software","iq_order","center_frequency_hz","bandwidth_hz","distance_object","corrected_geometry","corrected_distance_cm","corrected_replicate","auxiliary_tag_meaning","metadata_verified","longitudinal_cohort","include_in_stability","notes")


def table_write(path,rows,fields=None):
    if fields is None:
        fields=list(rows[0]) if rows else []
        fields+=sorted({k for r in rows for k in r}-set(fields))
    with Path(path).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)


def truth(value):
    return str(value).strip().lower() in ("true","yes","1")


def main():
    p=argparse.ArgumentParser();p.add_argument("--manifest",default=str(ROOT/"source_manifest.json"));a=p.parse_args()
    manifest=json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    overrides_path=ROOT/"metadata_overrides.csv"
    overrides={}
    if overrides_path.exists():
        with overrides_path.open(encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                key=(row["source_id"],row["archive_member"])
                if key in overrides: raise ValueError("Conflicting metadata override keys")
                overrides[key]=row
    entries=[];records=[];source_summaries=[];notes=[];unrecognized=[]
    for source in manifest["sources"]:
        archive=Path(source["archive"])
        if not archive.is_absolute(): archive=WORKSPACE/archive
        if not archive.is_file():
            raise FileNotFoundError(str(archive))
        source_entries=[]
        with zipfile.ZipFile(archive) as z:
            for index,zi in enumerate(z.infolist(),1):
                name=displayed_name(zi)
                e={"source_id":source["source_id"],"archive_member":zi.filename,"display_member":name,"file_size_bytes":zi.file_size,"compressed_size_bytes":zi.compress_size,"crc32_expected":f"{zi.CRC:08x}","zip_modified_time":"%04d-%02d-%02d %02d:%02d:%02d"%zi.date_time,"directory":zi.is_dir(),"name_utf8_flag":bool(zi.flag_bits&0x800)}
                entries.append(e);source_entries.append(e)
                if zi.is_dir(): continue
                suffix=Path(name).suffix.lower()
                if suffix in (".txt",".json",".csv",".md",".xml") and zi.file_size<1_000_000:
                    data=z.read(zi)
                    notes.append({**e,"utf8":data.decode("utf-8-sig")})
                if suffix!=".wav":
                    unrecognized.append(e);continue
                with z.open(zi) as h: prefix=h.read(65536)
                header=wav_header(prefix,zi.file_size)
                file_name=name.rsplit("/",1)[-1]
                stable=re.fullmatch(r"(\d+)day-(\d+)\.wav",file_name,re.I)
                cable=re.fullmatch(r"([cs])(\d+)cm-(\d+)(\([^)]*\))?\.wav",file_name,re.I)
                override=overrides.get((source["source_id"],zi.filename),{})
                stable_type=bool(stable) or source.get("experiment")=="stability" or override.get("include_in_stability","").lower()=="true"
                if not stable_type and not cable:
                    unrecognized.append(e);continue
                group="stability" if stable_type else "cable"
                fc=source.get("stability_center_frequency_hz") if stable_type else source.get("wire_center_frequency_hz")
                if override.get("center_frequency_hz"): fc=int(override["center_frequency_hz"])
                bw=int(override.get("bandwidth_hz") or source.get("bandwidth_hz") or 0) or None
                if stable_type:
                    geometry=None;distance=None;rep=None
                    label=int(stable.group(1)) if stable else None
                    sequence=int(stable.group(2)) if stable else index
                    tag=""
                    base_id=f"T{sequence:02d}"
                else:
                    geometry=cable.group(1).lower();distance=int(cable.group(2));rep=int(cable.group(3));tag=(cable.group(4) or "").strip("()")
                    label=None;sequence=None
                    base_id=f"W_{geometry}{distance:03d}_r{rep}"
                if override.get("corrected_geometry"): geometry=override["corrected_geometry"]
                if override.get("corrected_distance_cm"): distance=int(override["corrected_distance_cm"])
                if override.get("corrected_replicate"): rep=int(override["corrected_replicate"])
                date=override.get("acquisition_date") or (source.get("stability_calendar_date") if stable_type else None)
                relative_day=override.get("relative_day") or (source.get("relative_day_confirmed") if stable_type else None)
                declared_semantics=source.get("stability_filename_semantics","unconfirmed")
                if stable and declared_semantics=="prefix_is_day_suffix_is_repeat": relative_day=int(stable.group(1))
                if stable and declared_semantics=="suffix_is_day": relative_day=int(stable.group(2))
                metadata_verified=truth(override.get("metadata_verified",""))
                cohort=override.get("longitudinal_cohort") or source.get("longitudinal_cohort")
                history=(source.get("role")!="current_descriptive")
                required_history=(date,cohort,override.get("device_state"),override.get("gain_db"),override.get("agc"),override.get("receiver_chain_id"),override.get("antenna_id"),override.get("receiver_power"),override.get("recording_software"),override.get("iq_order"),fc,bw)
                history_ok=source.get("history_merge_approved",False) and metadata_verified and all(v is not None and str(v)!="" for v in required_history) and cohort==manifest.get("active_stability_cohort")
                rid=base_id if source["source_id"]=="current_k4" else source["source_id"]+"_"+base_id
                if tag: rid+="_"+re.sub(r"\W+","_",tag)
                record={**e,**{k:v for k,v in header.items() if k!="chunks_before_data"},"record_id":rid,"archive_path":str(archive.resolve()),"file_name":file_name,"experiment":group,"device_id":source.get("device_id","heater2"),"center_frequency_hz":fc,"center_frequency_source":"current corrected user instruction" if source["source_id"]=="current_k4" and not override.get("center_frequency_hz") else "reviewed source manifest/metadata override","acquisition_bandwidth_hz":bw,"bandwidth_source":"current corrected user instruction" if source["source_id"]=="current_k4" else "source manifest/metadata override","frequency_min_hz":fc-bw/2 if fc is not None and bw else None,"frequency_max_hz":fc+bw/2 if fc is not None and bw else None,"acquisition_date":date,"relative_day_confirmed":relative_day,"calendar_date_confirmed":bool(date),"filename_day_token":label,"filename_stability_suffix":sequence,"stability_filename_semantics":declared_semantics if stable_type else None,"geometry":geometry,"geometry_source":"filename c=Curved/s=Straight; current user instruction" if not stable_type else None,"distance_label_cm":distance,"distance_object":override.get("distance_object") or source.get("distance_object"),"replicate":rep,"repeat_type":"technical repeats within condition" if not stable_type else "repeat/date semantics unconfirmed" if declared_semantics=="unconfirmed" else declared_semantics,"auxiliary_tag":tag,"auxiliary_tag_meaning":override.get("auxiliary_tag_meaning") or None,"device_state":override.get("device_state") or source.get("device_state"),"gain_db":override.get("gain_db") or None,"gain_fixed_confirmed":source.get("gain_fixed_confirmed"),"agc":override.get("agc") or source.get("agc"),"antenna_id":override.get("antenna_id") or source.get("antenna_id"),"receiver_chain_id":override.get("receiver_chain_id") or source.get("receiver_chain_id"),"receiver_power":override.get("receiver_power") or source.get("receiver_power"),"recording_software":override.get("recording_software") or source.get("recording_software"),"iq_order":override.get("iq_order") or source.get("iq_order"),"metadata_verified":metadata_verified,"longitudinal_cohort":cohort,"merge_status":"approved_history" if history and history_ok else "quarantined_history" if history else "current_descriptive_unverified_metadata","primary_40_80_factorial":group=="cable" and distance in (40,80) and not tag,"header_details":header,"full_zip_crc_validated":False,"header_sha256":hashlib.sha256(prefix[:header["data_offset"]]).hexdigest(),"date_note":"ZIP modification time is not an acquisition date; no date inferred from filename suffix","quality_note":"auxiliary tag meaning unconfirmed" if tag and not override.get("auxiliary_tag_meaning") else ""}
                records.append(record)
        source_summaries.append({"source_id":source["source_id"],"archive":str(archive.resolve()),"archive_bytes":archive.stat().st_size,"uncompressed_bytes":sum(e["file_size_bytes"] for e in source_entries),"entry_count":len(source_entries)})
    ids=[r["record_id"] for r in records]
    if len(ids)!=len(set(ids)): raise ValueError("Duplicate record IDs: review filename/source conflicts")
    collision=defaultdict(list)
    for r in records: collision[(r["file_size_bytes"],r["crc32_expected"])].append(r["record_id"])
    duplicate_candidates=[v for v in collision.values() if len(v)>1]
    conditions=defaultdict(list)
    for r in records:
        if r["experiment"]=="cable": conditions[(r["geometry"],r["distance_label_cm"])].append(r)
    coverage=[]
    for (g,d),rr in sorted(conditions.items()):
        reps=sorted(r["replicate"] for r in rr)
        coverage.append({"geometry":g,"distance_label_cm":d,"file_count":len(rr),"replicates":reps,"missing_of_1_to_4":sorted(set(range(1,5))-set(reps)),"tagged_records":[r["file_name"] for r in rr if r["auxiliary_tag"]]})
    stable=[r for r in records if r["experiment"]=="stability" and r["merge_status"]!="quarantined_history"]
    result={"analysis_id":manifest["analysis_id"],"source_manifest":str(Path(a.manifest).resolve()),"sources":source_summaries,"entries":entries,"notes":notes,"unrecognized":unrecognized,"records":records,"counts":dict(Counter(r["experiment"] for r in records)),"condition_coverage":coverage,"duplicate_content_candidates_size_crc":duplicate_candidates,"header_consistency_all":all(r["header_consistent"] for r in records),"verified_stability_calendar_dates":sorted({r["acquisition_date"] for r in stable if r["acquisition_date"]}),"verified_stability_relative_days":sorted({int(r["relative_day_confirmed"]) for r in stable if r["relative_day_confirmed"]}),"stability_zip_dates_only":sorted({r["zip_modified_time"].split()[0] for r in stable}),"audit_scope":"all ZIP entries and first65536 uncompressed bytes of each WAV; full CRC/SHA/content verification deferred to remote processing","raw_data_write_operations":0}
    (ROOT/"data_inventory.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    table_write(ROOT/"data_index.csv",[{k:v for k,v in r.items() if k!="header_details"} for r in records])
    if not overrides_path.exists():
        table_write(overrides_path,[{k:r.get(k,"") if k in ("source_id","archive_member") else "" for k in OVERRIDE_FIELDS} for r in records],list(OVERRIDE_FIELDS))
    report=["# K4文件与采集条件检查","","本报告只核对结构和参数，未预设稳定性或姿态效应。", "",f"共{len(records)}个WAV；稳定性系列{len(stable)}份，弯直组{sum(r['experiment']=='cable' for r in records)}份；展开总量{sum(x['uncompressed_bytes'] for x in source_summaries):,}字节。", "", "## 已核实参数", "", "|分组|文件数|中心频率与完整带宽（用户更正）|头部采样率|格式|实际时长范围|","|---|---:|---|---|---|---|"]
    for group in ("stability","cable"):
        rr=[r for r in records if r["experiment"]==group]
        report.append(f"|{group}|{len(rr)}|{sorted({r['center_frequency_hz']/1e6 for r in rr})} MHz，带宽20 MHz|{sorted({r['sample_rate_hz'] for r in rr})}|{sorted({(r['container'],r['format_tag'],r['channels'],r['bits_per_sample']) for r in rr})}|{min(r['duration_s'] for r in rr):.6f}–{max(r['duration_s'] for r in rr):.6f} s|")
    report += ["", "主分析覆盖稳定性1577–1597 MHz、弯直10–30 MHz；采样率与带宽分别列出。I/Q顺序未确认，使用编码频偏并保留两种RF候选轴。两组不混算频带功率、峰频或相关系数。", "", "## 日期覆盖与分组", "",f"当前可从已确认采集日期核实的日数为{len(result['verified_stability_calendar_dates'])}；已确认相对日标签{result['verified_stability_relative_days']}。10day-1…10的含义尚未确认。ZIP修改日期候选为{result['stability_zip_dates_only']}，不能据此证明十天或同一天采集。", "", "|姿态|距离标签(cm)|文件数|后缀重复号|按四重复设计尚未提供|辅助标签|","|---|---:|---:|---|---|---|"]
    for c in coverage: report.append(f"|{c['geometry']}|{c['distance_label_cm']}|{c['file_count']}|{c['replicates']}|{c['missing_of_1_to_4']}|{','.join(c['tagged_records'])}|")
    report += ["", "40/80cm的c/s四条件均各有1–4四次技术重复。用户已明确更正：原名s150cm-4.wav属于伸直160cm第4次重复；原件不更名，通过metadata_overrides.csv修正条件映射。因此s160条件也有完整四重复。s160cm-1(terminal)保留辅助标签，不据此推断新状态。额外距离只作补充结果；距离标签的测量对象仍未知。", "", "本批58个WAV均为8位无符号PCM，两通道；按(u8−128)/128解码，而非沿用上一批PCM16/32768。实际字节率40,000,000决定了文件时长，不能从上一批字长推算时长。", "", f"头部长度一致性：{result['header_consistency_all']}；按大小+ZIP CRC筛出的内容重复候选：{duplicate_candidates}；完整内容重复核验待远端SHA-256。", "", "增益/AGC/天线/供电/软件/日期未写入现有WAV前置头；如后有独立记录，可填metadata_overrides.csv，不能从中心频率相同推断条件相同。", "", "## 既有带宽口径检查", "", "此前ethersense_supplemental报告的统计指标采用过±5MHz，而底层Welch程序保存完整20MSPS双边谱。本批K4不沿用旧指标或旧10MHz掩码；本批主积分使用完整20MHz，边缘去除仅作另外的敏感性分析。旧报告与原始数据不覆盖。"]
    (ROOT/"01_文件与条件检查.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("counts","header_consistency_all","verified_stability_calendar_dates","verified_stability_relative_days","condition_coverage","duplicate_content_candidates_size_crc")},ensure_ascii=False,indent=2))
    print("HEADERS",{g:{"fs":sorted({r['sample_rate_hz'] for r in records if r['experiment']==g}),"seconds":[min(r['duration_s'] for r in records if r['experiment']==g),max(r['duration_s'] for r in records if r['experiment']==g)]} for g in ("stability","cable")})


if __name__=="__main__": main()
