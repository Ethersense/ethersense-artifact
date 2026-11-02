"""Stream every RF64 I/Q sample on the selected remote CPU node.

Channel 1 + j*channel 2 is an explicitly provisional convention, not a claim
about the recorder. Output stays on the baseband offset axis for re-mapping.
"""
from __future__ import print_function

import argparse
import concurrent.futures
import hashlib
import json
import os
import time
import zipfile
from pathlib import Path

import numpy as np
import scipy
from scipy import fft, signal

NPERSEG = 65536
HOP = NPERSEG // 2
CHUNK_FRAMES = 2 ** 21
TEMPORAL_BINS = 16
FFT_BATCH = 16


def record_id(record):
    groups = {"导线实验": "A", "导线实验2（沿着导线1-10m）": "B", "并联实验": "C"}
    return "%s%02d" % (groups[record["experiment_folder"]], record["chronological_index"])


def one_record(archive, record, output):
    start_wall = time.time()
    rid = record_id(record)
    fs = record["sample_rate_hz"]
    samples = record["sample_frames"]
    if record["format_tag"] != 1 or record["channels"] != 2 or record["bits_per_sample"] != 16:
        raise ValueError("Unsupported format, not silently converted")
    window = signal.get_window("hann", NPERSEG, fftbins=True).astype(np.float32)
    factor = 1.0/(fs * np.sum(window.astype(np.float64)**2))
    sum_psd = np.zeros(NPERSEG, dtype=np.float64)
    temporal_sum = np.zeros((TEMPORAL_BINS, NPERSEG), dtype=np.float64)
    temporal_count = np.zeros(TEMPORAL_BINS, dtype=np.int64)
    sha = hashlib.sha256()
    total_frames, total_segments, base_frame = 0, 0, 0
    sum_channels = np.zeros(2, dtype=np.float64)
    sum_square = np.zeros(2, dtype=np.float64)
    cross_sum = 0.0
    zero_samples, near_endpoint_samples, max_abs = 0, 0, 0
    first_lsb_counts = None
    reference_relative_error = None
    carry = np.empty(0, dtype=np.complex64)
    with zipfile.ZipFile(archive) as z:
        with z.open(record["archive_member"]) as handle:
            header = handle.read(record["data_offset"])
            sha.update(header)
            remaining = record["data_bytes"]
            while remaining:
                raw = handle.read(min(remaining, CHUNK_FRAMES * 4))
                if not raw or len(raw) % 4:
                    raise ValueError("Truncated or unaligned PCM payload")
                sha.update(raw)
                remaining -= len(raw)
                arr = np.frombuffer(raw, dtype="<i2").reshape(-1, 2)
                total_frames += len(arr)
                scaled = arr.astype(np.float32) / 32768.0
                sum_channels += scaled.sum(axis=0, dtype=np.float64)
                sum_square += (scaled*scaled).sum(axis=0, dtype=np.float64)
                cross_sum += np.sum(scaled[:,0]*scaled[:,1], dtype=np.float64)
                absolute = np.abs(arr.astype(np.int32))
                max_abs = max(max_abs, int(absolute.max()))
                zero_samples += int(np.count_nonzero(arr == 0))
                near_endpoint_samples += int(np.count_nonzero(absolute >= 32766))
                if first_lsb_counts is None:
                    first_lsb_counts = np.bincount(np.bitwise_and(arr.ravel()[:524288], 255), minlength=256).tolist()
                iq = scaled[:,0].astype(np.complex64)
                iq.imag = scaled[:,1]
                buf = np.concatenate((carry, iq)) if carry.size else iq
                nseg = max(0, (len(buf)-NPERSEG)//HOP + 1)
                if reference_relative_error is None and nseg >= 3:
                    reference_slice = buf[:NPERSEG+2*HOP]
                    ref_freq, ref_psd = signal.welch(reference_slice, fs=fs, window=window, nperseg=NPERSEG, noverlap=NPERSEG-HOP, detrend="constant", return_onesided=False, scaling="density", average="mean")
                    sample_frames = np.stack([reference_slice[k*HOP:k*HOP+NPERSEG] for k in range(3)])
                    sample_frames -= sample_frames.mean(axis=1, keepdims=True)
                    transformed = fft.fft(sample_frames*window, axis=1, workers=1)
                    custom = (transformed.real**2+transformed.imag**2).mean(axis=0)*factor
                    reference_relative_error = float(np.max(np.abs(custom-ref_psd))/np.max(ref_psd))
                    if reference_relative_error > 1e-5:
                        raise ValueError("Reference Welch normalization check failed")
                for first in range(0, nseg, FFT_BATCH):
                    count = min(FFT_BATCH, nseg-first)
                    first_sample = first*HOP
                    frames = np.lib.stride_tricks.as_strided(buf[first_sample:], shape=(count,NPERSEG), strides=(buf.strides[0]*HOP,buf.strides[0]), writeable=False).copy()
                    frames -= frames.mean(axis=1, keepdims=True)
                    frames *= window
                    transformed = fft.fft(frames, axis=1, workers=1)
                    periodograms = (transformed.real**2+transformed.imag**2)*factor
                    sum_psd += periodograms.sum(axis=0, dtype=np.float64)
                    segment_centers = base_frame+(first+np.arange(count))*HOP+NPERSEG/2
                    bins = np.minimum(TEMPORAL_BINS-1, (segment_centers/samples*TEMPORAL_BINS).astype(int))
                    for tb in np.unique(bins):
                        selected = bins == tb
                        temporal_sum[tb] += periodograms[selected].sum(axis=0, dtype=np.float64)
                        temporal_count[tb] += int(selected.sum())
                    total_segments += count
                consumed = nseg*HOP
                carry = buf[consumed:].copy()
                base_frame += consumed
            tail = handle.read()
            sha.update(tail)
            if tail:
                raise ValueError("Unexpected trailing bytes, header audit must be updated")
    if total_frames != samples or samples != record.get("rf64_sample_frames",samples):
        raise ValueError("Sample count does not match RF64 ds64")
    if np.any(temporal_count == 0):
        raise ValueError("Empty temporal bin")
    mean_psd = fft.fftshift(sum_psd/total_segments)
    time_psd = fft.fftshift(temporal_sum/temporal_count[:,None],axes=1)
    offset = fft.fftshift(fft.fftfreq(NPERSEG,1.0/fs))
    means = sum_channels/samples
    variance = sum_square/samples-means**2
    corr = (cross_sum/samples-means[0]*means[1])/np.sqrt(variance.prod())
    output = Path(output)
    np.savez_compressed(str(output/(rid+"_spectra.npz")), offset_hz=offset, mean_psd=mean_psd, time_psd=time_psd.astype(np.float32), time_centers_s=(np.arange(TEMPORAL_BINS)+.5)*record["duration_s"]/TEMPORAL_BINS, temporal_segment_count=temporal_count)
    meta = {"record_id":rid,"file_name":record["file_name"],"archive_member":record["archive_member"],"full_zip_crc_validated":True,"sha256_uncompressed_wav":sha.hexdigest(),"sample_frames_processed":samples,"welch_segments":total_segments,"unused_final_sample_frames":samples-(total_segments-1)*HOP-NPERSEG,"duration_s":record["duration_s"],"sample_rate_hz":fs,"fft_length":NPERSEG,"frequency_bin_hz":fs/NPERSEG,"hann_enbw_hz":1.5*fs/NPERSEG,"overlap_samples":NPERSEG-HOP,"temporal_bins":TEMPORAL_BINS,"iq_convention":"unconfirmed channel_1 + j*channel_2; preserve offset axis","amplitude_normalization":"signed PCM16 / 32768, digital units; no dBm calibration","detrend":"per-segment complex mean removal; no TMF/whitening/VMD","raw_mean_square_complex":float(sum_square.sum()/samples),"full_band_welch_integral":float(mean_psd.sum()*fs/NPERSEG),"channel_means":means.tolist(),"channel_variances":variance.tolist(),"channel_correlation":float(corr),"maximum_absolute_pcm":max_abs,"zero_channel_sample_fraction":zero_samples/(samples*2),"pcm_endpoint_fraction":near_endpoint_samples/(samples*2),"first_chunk_lsb_counts":first_lsb_counts,"reference_welch_relative_error":reference_relative_error,"wall_seconds":time.time()-start_wall}
    (output/(rid+"_quality.json")).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers",type=int,default=4)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    started = time.time()
    print("START",time.strftime("%Y-%m-%d %H:%M:%S %z"),"files",len(inventory["records"]),"workers",args.workers,flush=True)
    records = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(one_record,args.archive,r,args.output) for r in inventory["records"]]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            records.append(result)
            print("DONE",result["record_id"],result["file_name"],"seconds",round(result["wall_seconds"],2),"segments",result["welch_segments"],"CRC OK",flush=True)
    manifest = {"status":"complete","archive":args.archive,"record_count":len(records),"records":sorted(records,key=lambda x:x["record_id"]),"versions":{"numpy":np.__version__,"scipy":scipy.__version__},"workers":args.workers,"wall_seconds":time.time()-started,"all_crc_validated":all(r["full_zip_crc_validated"] for r in records),"max_reference_welch_relative_error":max(r["reference_welch_relative_error"] for r in records)}
    (output/"compute_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("COMPLETE",len(records),"seconds",round(manifest["wall_seconds"],2),flush=True)


if __name__ == "__main__":
    main()
