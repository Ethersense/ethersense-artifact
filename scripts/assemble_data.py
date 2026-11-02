#!/usr/bin/env python3
"""Reassemble the released ZIP archives from verified anonymous-review data parts."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def assemble(root=ROOT):
    indexes = sorted((root / 'data/metadata/parts').glob('*.json'))
    legacy = root / 'data/metadata/review_parts.json'
    if legacy.is_file():
        indexes.insert(0, legacy)
    archives = {}
    for path in indexes:
        for item in json.loads(path.read_text(encoding='utf-8'))['archives']:
            archives[item['path']] = item
    if not archives:
        raise FileNotFoundError('No released data-part manifest found.')
    for item in archives.values():
        dest = root / item['path']
        if dest.is_file() and dest.stat().st_size == item['bytes'] and digest(dest) == item['sha256']:
            print('Already verified:', item['path'])
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(dest.name + '.assembling')
        if temporary.exists():
            raise FileExistsError('Inspect the existing incomplete output before retrying: ' + str(temporary))
        whole = hashlib.sha256()
        size = 0
        try:
            with temporary.open('xb') as output:
                for part in item['parts']:
                    source = root / part['path']
                    h = hashlib.sha256()
                    part_size = 0
                    with source.open('rb') as f:
                        for block in iter(lambda: f.read(1024 * 1024), b''):
                            h.update(block)
                            whole.update(block)
                            part_size += len(block)
                            size += len(block)
                            output.write(block)
                    if part_size != part['bytes'] or h.hexdigest() != part['sha256']:
                        raise ValueError('Missing, truncated or corrupted data part: ' + part['path'])
            if size != item['bytes'] or whole.hexdigest() != item['sha256']:
                raise ValueError('Reassembled archive checksum mismatch: ' + item['path'])
            os.replace(temporary, dest)
        except BaseException:
            if temporary.exists():
                temporary.unlink()
            raise
        print('Assembled and verified:', item['path'])

if __name__ == '__main__':
    assemble()
