#!/usr/bin/env python3
"""Verify only the explicitly released archives, without decompressing the raw payload."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'data/metadata/release_datasets.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validate(root=ROOT):
    manifest = json.loads((root / INDEX.relative_to(ROOT)).read_text(encoding='utf-8'))
    problems = []
    datasets = []
    for dataset in manifest['datasets']:
        path = root / dataset['path']
        row = {'id': dataset['id'], 'path': dataset['path'], 'ok': False}
        datasets.append(row)
        if not path.is_file():
            problems.append(f'Missing archive: {dataset["path"]}. Run git lfs pull.')
            continue
        with path.open('rb') as f:
            prefix = f.read(100)
        if prefix.startswith(b'version https://git-lfs.github.com/spec/v1'):
            problems.append(f'LFS pointer found instead of data: {dataset["path"]}. Run git lfs pull.')
            continue
        if path.stat().st_size != dataset['bytes'] or digest(path) != dataset['sha256']:
            problems.append(f'Archive SHA-256/size mismatch: {dataset["path"]}')
            continue
        try:
            with zipfile.ZipFile(path) as z:
                entries = [i for i in z.infolist() if not i.is_dir()]
                expected = {r['archive_member']: r for r in dataset['records']}
                if set(i.filename for i in entries) != set(expected):
                    problems.append(f'ZIP entry set mismatch: {dataset["path"]}')
                    continue
                entry_problems = []
                for i in entries:
                    r = expected[i.filename]
                    if i.file_size != r['bytes'] or f'{i.CRC:08x}' != r['zip_crc32']:
                        entry_problems.append(i.filename)
                    if r['analysis_included'] and r['data_bytes'] == 0:
                        entry_problems.append(i.filename + ': empty but included')
                if entry_problems:
                    problems.append(f'Entry metadata mismatch: {entry_problems}')
                    continue
        except (OSError, zipfile.BadZipFile) as e:
            problems.append(f'ZIP read failed: {dataset["path"]}: {e}')
            continue
        row.update(ok=True, sha256=dataset['sha256'], bytes=dataset['bytes'],
                   wav_entries=len(entries), analysis_included=sum(r['analysis_included'] for r in dataset['records']))
    return {'ok': not problems, 'datasets': datasets, 'problems': problems,
            'checks': ['archive byte count', 'archive SHA-256', 'ZIP directory entry set/size/CRC metadata', 'inclusion flags'],
            'payload_decompressed': False, 'full_payload_crc_recomputed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', help='Optional report path; no output file is written by default.')
    args = parser.parse_args()
    report = validate()
    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
