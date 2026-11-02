"""Read-only, header-only audit of the uploaded EtherSense supplemental ZIP."""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import struct
import zipfile
from collections import Counter
from pathlib import Path


def displayed_name(info):
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("gbk")
    except (UnicodeError, LookupError):
        return info.filename


def wav_header(prefix, file_size):
    if prefix[:4] not in (b"RIFF", b"RF64") or prefix[8:12] != b"WAVE":
        raise ValueError("Not a RIFF/RF64 WAVE header")
    out = {"container": prefix[:4].decode("ascii"), "riff_bytes": struct.unpack_from("<I", prefix, 4)[0] + 8}
    chunks = []
    pos = 12
    while pos + 8 <= len(prefix):
        tag, size = struct.unpack_from("<4sI", prefix, pos)
        start = pos + 8
        chunk = {"id": tag.decode("ascii", errors="backslashreplace"), "offset": pos, "size": size}
        chunks.append(chunk)
        if tag == b"data":
            effective_size = out.get("rf64_data_bytes", size) if size == 0xffffffff else size
            out.update(data_offset=start, data_bytes=effective_size, data_bytes_32_placeholder=size, trailing_bytes=file_size-start-effective_size)
            break
        body = prefix[start:start+size]
        chunk["body_base64"] = base64.b64encode(body).decode("ascii")
        if tag == b"ds64" and len(body) >= 28:
            riff64, data64, samples64, table_len = struct.unpack_from("<QQQI", body)
            out.update(riff_bytes_32_placeholder=out["riff_bytes"], riff_bytes=riff64+8, rf64_data_bytes=data64, rf64_sample_frames=samples64, rf64_table_length=table_len)
        if tag == b"fmt " and len(body) >= 16:
            fmt, chans, fs, byte_rate, align, bits = struct.unpack_from("<HHIIHH", body)
            out.update(format_tag=fmt, channels=chans, sample_rate_hz=fs, byte_rate=byte_rate, block_align=align, bits_per_sample=bits)
            if fmt == 0xfffe and len(body) >= 40:
                out["extensible_subformat_guid_hex"] = body[24:40].hex()
        if tag in (b"LIST", b"bext", b"auxi", b"iXML", b"xml "):
            chunk["printable_ascii"] = "".join(chr(b) if 32 <= b < 127 else f"\\x{b:02x}" for b in body)
        if start + size > len(prefix):
            out["header_inspection_incomplete"] = True
            break
        pos = start + size + (size % 2)
    if "data_bytes" in out and "sample_rate_hz" in out:
        out["sample_frames"] = out["data_bytes"] // out["block_align"]
        out["duration_s"] = out["sample_frames"] / out["sample_rate_hz"]
        out["header_consistent"] = (out["data_bytes"] % out["block_align"] == 0 and out["byte_rate"] == out["sample_rate_hz"]*out["block_align"] and out["riff_bytes"] == file_size)
    out["chunks_before_data"] = chunks
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default="attachments/补充实验数据.zip")
    parser.add_argument("--output", default="results/ethersense_supplemental")
    args = parser.parse_args()
    archive = Path(args.archive)
    dest = Path(args.output)
    dest.mkdir(parents=True, exist_ok=True)
    entries, waves, notes = [], [], []
    with zipfile.ZipFile(archive) as z:
        for zi in z.infolist():
            name = displayed_name(zi)
            entry = {"archive_member": name, "file_size_bytes": zi.file_size, "compressed_size_bytes": zi.compress_size, "crc32_expected": f"{zi.CRC:08x}", "zip_timestamp": "%04d-%02d-%02d %02d:%02d:%02d" % zi.date_time, "directory": zi.is_dir(), "compression_type": zi.compress_type, "name_utf8_flag": bool(zi.flag_bits & 0x800)}
            entries.append(entry)
            if zi.is_dir():
                continue
            if name.lower().endswith(".txt"):
                content = z.read(zi)
                notes.append({**entry, "raw_base64": base64.b64encode(content).decode("ascii"), "text_utf8": content.decode("utf-8-sig")})
            if not name.lower().endswith(".wav"):
                continue
            with z.open(zi) as stream:
                prefix = stream.read(65536)
            hdr = wav_header(prefix, zi.file_size)
            file_name = name.rsplit("/", 1)[-1]
            match = re.match(r"(?P<h>\d{2})-(?P<m>\d{2})-(?P<s>\d{2})_(?P<f>\d+)Hz(?:_(?P<state>.+))?\.wav$", file_name)
            if not match:
                raise ValueError(f"Unrecognized WAV name: {file_name}")
            parts = match.groupdict()
            group = name.split("/")[-2]
            record = {**entry, **{k:v for k,v in hdr.items() if k != "chunks_before_data"}, "file_name": file_name, "experiment_folder": group, "filename_time": f'{parts["h"]}:{parts["m"]}:{parts["s"]}', "center_frequency_hz": int(parts["f"]), "condition_filename": parts["state"] or "", "header_details": hdr, "reported_rf_bandwidth_hz": 10_000_000, "reported_bandwidth_source": "current user instruction (not an embedded gain/filter record)", "rf_gain_db": None, "if_gain_db": None, "lna_gain_db": None, "agc": None, "iq_channel_order": "unconfirmed", "frequency_axis_orientation": "unconfirmed until I/Q order is established", "measurement_date": None, "date_candidate": entry["zip_timestamp"].split(" ")[0], "date_status": "ZIP member modification date only; not confirmed acquisition date", "timezone": "unknown", "full_zip_crc_validated": False}
            waves.append(record)
    for group in sorted(set(w["experiment_folder"] for w in waves)):
        group_waves = sorted((w for w in waves if w["experiment_folder"] == group), key=lambda w:w["filename_time"])
        for idx, w in enumerate(group_waves):
            w["chronological_index"] = idx + 1
            if group == "导线实验":
                distances = [4,3,2,1,-1,-2,-3,-4,None]
                w["distance_m"] = distances[idx] if len(group_waves) == 9 else None
                w["condition"] = "background_base" if idx == 8 else ("wire_positive" if idx < 4 else "opposite_negative")
                w["condition_source"] = "user acquisition sequence + folder TXT; chronological filename order"
            elif group.startswith("导线实验2"):
                w["distance_m"] = idx + 1 if len(group_waves) == 10 else None
                w["condition"] = "wire_positive_distance"
                w["condition_source"] = "user 1 to 10 m chronological order; receiver distance referenced to e-bike per user"
            else:
                w["distance_m"] = None
                w["condition"] = w["condition_filename"]
                w["condition_source"] = "filename literal label; 电器2 identity and connectivity protocol pending confirmation"
            w["sampled_frequency_min_hz"] = w["center_frequency_hz"] - w["sample_rate_hz"]/2
            w["sampled_frequency_max_hz"] = w["center_frequency_hz"] + w["sample_rate_hz"]/2
            w["reported_passband_min_hz"] = w["center_frequency_hz"] - w["reported_rf_bandwidth_hz"]/2
            w["reported_passband_max_hz"] = w["center_frequency_hz"] + w["reported_rf_bandwidth_hz"]/2
            w["gain_comparability"] = "not established; gain/AGC/filter settings missing from pre-data header"
    result = {"archive": str(archive.resolve()), "archive_size_bytes": archive.stat().st_size, "entry_count": len(entries), "uncompressed_bytes": sum(x["file_size_bytes"] for x in entries), "wav_count": len(waves), "notes_count": len(notes), "group_counts": dict(Counter(w["experiment_folder"] for w in waves)), "entries": entries, "notes": notes, "records": waves, "audit_scope": "First 65536 uncompressed bytes per WAV; data contents/CRC/trailing chunks are not audited here."}
    (dest/"data_inventory.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    fields = [k for k in waves[0] if k != "header_details"]
    fields += sorted({k for w in waves for k in w if k != "header_details"} - set(fields))
    with (dest/"data_index.csv").open("w",encoding="utf-8-sig",newline="") as handle:
        writer = csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(waves)
    print(json.dumps({"wav_count":len(waves),"group_counts":result["group_counts"],"uncompressed_bytes":result["uncompressed_bytes"],"formats":sorted({w["format_tag"] for w in waves}),"sample_rates":sorted({w["sample_rate_hz"] for w in waves}),"channels":sorted({w["channels"] for w in waves}),"bits":sorted({w["bits_per_sample"] for w in waves}),"duration_range_s":[min(w["duration_s"] for w in waves),max(w["duration_s"] for w in waves)],"all_headers_consistent":all(w["header_consistent"] for w in waves),"trailing_bytes":sorted({w["trailing_bytes"] for w in waves}),"example_header":waves[0]["header_details"],"rows":[{k:w.get(k) for k in ("file_name","distance_m","condition","duration_s","sample_rate_hz")} for w in waves]},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
