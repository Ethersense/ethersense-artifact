"""Verbatim RF64 parser reused from the verified 2026-10-14 pipeline."""
import base64
import struct

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
