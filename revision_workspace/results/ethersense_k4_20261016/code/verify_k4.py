"""Real-data invariants for K4 axes, decoder, grouping, metrics and delivered files."""
from __future__ import annotations
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import runtime_limits
import numpy as np
import fitz
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent


def read(name):
    with (ROOT/name).open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))


def main():
    inv=json.loads((ROOT/'data_inventory.json').read_text(encoding='utf-8'))
    s=json.loads((ROOT/'analysis_summary.json').read_text(encoding='utf-8'))
    c=json.loads((ROOT/'output/compute_manifest.json').read_text(encoding='utf-8'))
    index={r['record_id']:r for r in inv['records']};metrics={r['record_id']:r for r in read('record_metrics.csv')}
    active=[r for r in inv['records'] if r['merge_status']!='quarantined_history'];checks=[]
    def check(name,value,detail=None):
        checks.append({'check':name,'passed':bool(value),'detail':detail})
    check('selected_files_have_complete_CRC_receipts',len(active)==c['record_count'] and all(r['full_zip_crc_validated'] for r in active) and c['all_crc_validated'])
    current=[r for r in active if r['source_id']=='current_k4']
    check('current_source_58_PCM8_stereo20MSPS',len(current)==58 and all(r['format_tag']==1 and r['bits_per_sample']==8 and r['channels']==2 and r['sample_rate_hz']==20_000_000 for r in current))
    check('current_source_bandwidth20MHz',all(r['acquisition_bandwidth_hz']==20_000_000 for r in current))
    check('distinct_RF_bands_not_mixed',all(r['center_frequency_hz']==(1587e6 if r['experiment']=='stability' else 20e6) for r in current))
    correction=[r for r in current if r['file_name']=='s150cm-4.wav']
    check('raw_s150_r4_is_condition_s160_r4',len(correction)==1 and correction[0]['geometry']=='s' and correction[0]['distance_label_cm']==160 and correction[0]['replicate']==4)
    conditions={}
    for r in current:
        if r['experiment']=='cable': conditions.setdefault((r['geometry'],r['distance_label_cm']),[]).append(r['replicate'])
    check('all12_cable_cells_have4_technical_repeats',len(conditions)==12 and all(sorted(v)==[1,2,3,4] for v in conditions.values()))
    check('primary_factorial_has16_recordings',sum(r['primary_40_80_factorial'] for r in current)==16)
    integrity=True;axes=True;powers=True;hist=True;sha=[];max_power_error=0;max_ac_error=0
    for r in active:
        rid=r['record_id'];q=json.loads((ROOT/'output'/(rid+'_quality.json')).read_text(encoding='utf-8'))
        with np.load(ROOT/'output'/(rid+'_spectra.npz')) as z:
            f=z['offset_hz'];p=z['mean_psd'];df=float(f[1]-f[0]);mask=np.abs(f)<=r['acquisition_bandwidth_hz']/2
            value=float(p[mask].sum()*df);expected=float(metrics[rid]['full_band_power_digital_unit2'])
            max_power_error=max(max_power_error,abs(value/expected-1));powers &= bool(np.isfinite(p).all() and (p>=0).all() and np.isclose(value,expected,rtol=1e-9))
            axes &= bool(len(f)==65536 and np.isclose(f[0],-r['sample_rate_hz']/2) and np.isclose(f[-1],r['sample_rate_hz']/2-df))
            if r['source_id']=='current_k4': axes &= int(mask.sum())==65536
            ac=sum(q['channel_variances']);max_ac_error=max(max_ac_error,abs(value/ac-1) if ac else 0)
        integrity &= q['full_zip_crc_validated'] and q['input_crc32_expected']==r['crc32_expected'] and q['input_file_bytes']==r['file_size_bytes'] and q['sample_frames_processed']==r['sample_frames']
        if r['bits_per_sample']==8: hist &= sum(q['storage_histogram_8bit'])==r['sample_frames']*r['channels']
        sha.append(q['sha256_uncompressed_wav'])
    check('raw_CRC_size_sample_count_match',integrity)
    check('full_twosided_fft_axes_and_all20MHz_bins',axes)
    check('reported_power_equals_full20MHz_PSD_integral',powers,{'max_relative_error':max_power_error})
    check('whole_file_code_histogram_counts_every_channel_sample',hist)
    check('no_identical_WAV_content',len(sha)==len(set(sha)))
    check('SciPy_Welch_reference_error_below1e_minus5',c['max_reference_welch_relative_error']<1e-5,c['max_reference_welch_relative_error'])
    decoder=json.loads((ROOT/'decoder_verification.json').read_text(encoding='utf-8'))
    check('PCM8_decoder_matches_real_sample_SciPy_read',decoder['sample_rate_match'] and decoder['unsigned_dtype'] and decoder['channels_and_values_match'])
    pair_rows=read('pairwise_similarity.csv')
    check('no_cross_experiment_correlation',all(index[r['record_a']]['experiment']==index[r['record_b']]['experiment'] for r in pair_rows))
    check('confirmed_date_count_uses_actual_dates',s['stability']['confirmed_date_count']==len({r['acquisition_date'] for r in active if r['experiment']=='stability' and r['acquisition_date']}))
    check('no_multiclass_accuracy_or_MacroF1_from_single_class',s['stability']['classification_accuracy_and_macro_f1'] is None)
    tracks=read('feature_tracking.csv')
    check('missing_peaks_have_no_fabricated_zero_displacement',all(r['frequency_shift_hz_if_detected']=='' for r in tracks if r['detected_above6db']!='True'))
    check('detected_peaks_are_local_maxima_not_search_boundary',all(r['local_maximum_candidate']=='True' and r['search_window_boundary']=='False' and abs(float(r['frequency_shift_hz_if_detected']))<5000 for r in tracks if r['detected_above6db']=='True'))
    fp=json.loads((ROOT/'figure_provenance.json').read_text(encoding='utf-8'));figchecks=[]
    for meta in fp:
        pdf=ROOT/'paper/figures'/(meta['figure']+'.pdf');png=pdf.with_suffix('.png')
        d=fitz.open(pdf);page=d[0];fonts=page.get_fonts(full=True);spans=[span for block in page.get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for span in line['spans'] if span['text'].strip()]
        outside=[span['text'] for span in spans if not (page.rect+(-.5,-.5,.5,.5)).contains(fitz.Rect(span['bbox']))]
        minsize=min((span['size'] for span in spans),default=0)
        with Image.open(png) as im: dpi=im.info.get('dpi',(0,0));dims=im.size
        fonts_ok=all('Type3' not in f[2] and bool(d.extract_font(f[0])[3]) for f in fonts)
        figchecks.append({'figure':meta['figure'],'pdf_width_in':page.rect.width/72,'min_pdf_font_pt':minsize,'embedded_fonts':fonts_ok,
                          'raster_images_in_pdf':len(page.get_images()),'out_of_bounds_text':outside,'png_dpi':dpi,'png_size':dims})
        check(meta['figure']+'_paper_size_fonts_vector_dpi',abs(page.rect.width/72-meta['width_inches'])<.01 and minsize>=7 and fonts_ok and not outside and len(page.get_images())==0 and dpi[0]>590)
        check(meta['figure']+'_output_hashes_match',hashlib.sha256(pdf.read_bytes()).hexdigest()==meta['pdf_sha256'] and hashlib.sha256(png.read_bytes()).hexdigest()==meta['png_sha256'])
        d.close()
    report=ROOT/'EtherSense_K4补充实验分析报告.pdf';d=fitz.open(report);report_text=''.join(p.get_text() for p in d)
    check('Chinese_report_contains_real_negative_power_values',str(round(s['stability']['power_db']['mean'],3)) in report_text)
    check('Chinese_report_has_all_six_main_figure_captions',all('K4-'+str(i) in report_text for i in range(1,7)))
    check('report_pdf_has_embedded_TrueType_font',all('Type3' not in f[2] for page in d for f in page.get_fonts()))
    pages=len(d);d.close()
    versions={p:importlib.metadata.version(p) for p in ('numpy','scipy','matplotlib','reportlab','Pillow','openpyxl','PyMuPDF')}
    (ROOT/'software_versions.json').write_text(json.dumps({'local':versions,'remote':c['versions']},indent=2),encoding='utf-8')
    result={'all_checks_passed':all(r['passed'] for r in checks),'checks':checks,'figure_details':figchecks,'report_pages':pages,
            'diagnostic_PSD_integral_vs_full_file_AC_variance_max_relative_difference':max_ac_error,
            'diagnostic_note':'Welch window weighting/detrending differs from whole-file AC variance; this is not an equality assertion',
            'not_verified':['calendar-date coverage and inter-date independence','gain/AGC consistency','physical frequency and power calibration','source attribution and mis-match risk'],
            'raw_data_modifications':0}
    (ROOT/'verification_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':result['all_checks_passed'],'check_count':len(checks),'failed':[r for r in checks if not r['passed']],'report_pages':pages},ensure_ascii=False,indent=2))
    if not result['all_checks_passed']: raise SystemExit(1)


if __name__=='__main__': main()
