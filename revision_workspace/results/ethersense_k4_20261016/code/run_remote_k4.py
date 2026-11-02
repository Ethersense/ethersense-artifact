"""Full raw-data verification and cached streaming spectra on the CPU node."""
from __future__ import print_function

import argparse
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import scipy
from verified_welch import one_record, NPERSEG, HOP


def signature(r):
    fields={k:r[k] for k in ("crc32_expected","file_size_bytes","sample_rate_hz","format_tag","bits_per_sample","channels","data_bytes")}
    fields.update(fft_length=NPERSEG,hop=HOP,decoder="PCM8-u8center128/PCM16-signed-v1",temporal_bins=16)
    return hashlib.sha256(json.dumps(fields,sort_keys=True).encode("utf-8")).hexdigest()


def compute(archive,r,output):
    meta=one_record(archive,r,output)
    meta.update(input_crc32_expected=r["crc32_expected"],input_file_bytes=r["file_size_bytes"],processing_signature=signature(r),experiment=r["experiment"],source_id=r["source_id"])
    Path(output,r["record_id"]+"_quality.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    return meta


def main():
    p=argparse.ArgumentParser();p.add_argument("--inventory",default="data_inventory.json");p.add_argument("--archives-dir",default="archives");p.add_argument("--output",default="output");p.add_argument("--workers",type=int,default=4);a=p.parse_args()
    inv=json.loads(Path(a.inventory).read_text(encoding="utf-8"));out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    jobs=[r for r in inv["records"] if r["merge_status"]!="quarantined_history"]
    started=time.time();done=[];todo=[]
    for r in jobs:
        meta_path=out/(r["record_id"]+"_quality.json");spec_path=out/(r["record_id"]+"_spectra.npz")
        if meta_path.exists() and spec_path.exists():
            m=json.loads(meta_path.read_text(encoding="utf-8"))
            if m.get("processing_signature")==signature(r) and m.get("full_zip_crc_validated"):
                done.append(m);continue
        todo.append(r)
    print("START",time.strftime("%Y-%m-%d %H:%M:%S %z"),"total",len(jobs),"cached",len(done),"pending",len(todo),"workers",a.workers,flush=True)
    with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
        fs=[pool.submit(compute,str(Path(a.archives_dir)/(r["source_id"]+".zip")),r,a.output) for r in todo]
        for f in concurrent.futures.as_completed(fs):
            m=f.result();done.append(m)
            print("DONE",len(done),"/",len(jobs),m["record_id"],m["file_name"],"seconds",round(m["wall_seconds"],1),"CRC OK",flush=True)
    manifest={"status":"complete","record_count":len(done),"records":sorted(done,key=lambda m:m["record_id"]),"workers":a.workers,"wall_seconds":time.time()-started,"all_crc_validated":all(m["full_zip_crc_validated"] for m in done),"max_reference_welch_relative_error":max(m["reference_welch_relative_error"] for m in done),"versions":{"numpy":np.__version__,"scipy":scipy.__version__},"integration_note":"spectra include full sampled20MHz; masks are applied only in downstream analysis"}
    (out/"compute_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("COMPLETE",len(done),"seconds",round(manifest["wall_seconds"],1),flush=True)


if __name__=="__main__": main()
