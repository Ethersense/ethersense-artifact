"""Reviewable, cache-aware updates; no automatic historical pooling or heavy local FFT.

audit: inspect every manifest source, quarantine unapproved histories.
refresh: snapshot existing small deliverables, audit, verify cached input signatures,
         then regenerate metrics/figures/reports. Missing full spectra require a
         newly scheduled remote job; this script never falls back to local raw FFT.
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import runtime_limits
from run_remote_k4 import signature

ROOT=Path(__file__).resolve().parent.parent


def call(script): subprocess.run([sys.executable,str(ROOT/'code'/script)],check=True)


def snapshot():
    destination=ROOT/'versions'/datetime.now().strftime('%Y%m%d_%H%M%S')
    destination.mkdir(parents=True,exist_ok=False)
    for item in ROOT.iterdir():
        if item.is_file() and item.suffix.lower() in ('.md','.csv','.json','.pdf','.xlsx'):
            shutil.copy2(item,destination/item.name)
    if (ROOT/'paper').exists(): shutil.copytree(ROOT/'paper',destination/'paper')
    shutil.copytree(ROOT/'code',destination/'code',ignore=shutil.ignore_patterns('__pycache__'))
    print('Preserved previous deliverables:',destination)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('audit','refresh','check-cache'));a=p.parse_args()
    if a.action=='refresh': snapshot()
    if a.action!='check-cache': call('audit_k4.py')
    if a.action=='audit': return
    inv=json.loads((ROOT/'data_inventory.json').read_text(encoding='utf-8'))
    selected=[r for r in inv['records'] if r['merge_status']!='quarantined_history']
    missing=[];cached=[]
    for r in selected:
        q=ROOT/'output'/(r['record_id']+'_quality.json');n=ROOT/'output'/(r['record_id']+'_spectra.npz')
        if not q.exists() or not n.exists(): missing.append(r['record_id']);continue
        m=json.loads(q.read_text(encoding='utf-8'))
        if m.get('processing_signature')!=signature(r) or not m.get('full_zip_crc_validated'):
            missing.append(r['record_id'])
        else: cached.append(m)
    if missing:
        print('Need remote full-content verification/FFT for:',', '.join(missing))
        print('Re-run pick_node.py; review node/port/key and remote directory in remote_k4.py, then push/run/pull. No local bulk fallback.')
        raise SystemExit(2)
    if a.action=='check-cache':
        print(f'All {len(cached)} active records have matching verified cache signatures; no writes or raw FFT.');return
    # Metadata-only updates preserve the actual full-content verification receipts.
    manifest_path=ROOT/'output/compute_manifest.json'
    old=json.loads(manifest_path.read_text(encoding='utf-8'))
    old.update(record_count=len(cached),records=cached,all_crc_validated=all(x['full_zip_crc_validated'] for x in cached),
               max_reference_welch_relative_error=max(x['reference_welch_relative_error'] for x in cached))
    manifest_path.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
    for name in ('analyze_k4.py','summarize_k4.py','plot_k4.py'):
        call(name)
    subprocess.run([sys.executable,str(ROOT/'code/build_deliverables_k4.py'),'--update'],check=True)
    call('verify_k4.py')
    call('package_k4.py')
    print('Updated actual-data results. Author must check date/cohort status before adopting longitudinal claims.')


if __name__=='__main__': main()
