#!/usr/bin/env python3
"""Release-scoped entry points: validate original ZIPs or inspect their WAV-header manifest.

No spectrum recomputation or original-paper classifier reproduction is implied.
"""
import argparse
import json
import struct
import sys
import zipfile

from validate_data import ROOT, validate


def wav_header(head):
    if head[:4] not in (b'RIFF', b'RF64'):
        raise ValueError('Not RIFF/RF64')
    pos, ds64, fmt = 12, None, None
    while pos + 8 <= len(head):
        cid, size = head[pos:pos + 4], struct.unpack_from('<I', head, pos + 4)[0]
        if cid == b'ds64':
            ds64 = struct.unpack_from('<QQQ', head, pos + 8)
        if cid == b'fmt ':
            fmt = struct.unpack_from('<HHIIHH', head, pos + 8)
        if cid == b'data':
            if fmt is None:
                raise ValueError('No fmt before data')
            if size == 0xffffffff:
                if ds64 is None:
                    raise ValueError('RF64 sentinel without ds64')
                size = ds64[1]
            return {'channels': fmt[1], 'sample_rate_hz': fmt[2], 'bits_per_sample': fmt[5],
                    'data_bytes': size, 'data_offset': pos + 8}
        pos += 8 + size + (size & 1)
    raise ValueError('No data chunk in header prefix')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['manifest', 'validate'])
    args = parser.parse_args()
    verification = validate()
    if not verification['ok'] or args.stage == 'validate':
        print(json.dumps(verification, ensure_ascii=False, indent=2))
        return 0 if verification['ok'] else 1
    index = json.loads((ROOT / 'data/metadata/release_datasets.json').read_text(encoding='utf-8'))
    rows = []
    for dataset in index['datasets']:
        with zipfile.ZipFile(ROOT / dataset['path']) as z:
            for r in dataset['records']:
                with z.open(r['archive_member']) as f:
                    header = wav_header(f.read(min(4096, r['bytes'])))
                for key in ('channels', 'sample_rate_hz', 'bits_per_sample', 'data_bytes'):
                    if header[key] != r[key]:
                        raise ValueError(f'Header mismatch: {r["archive_member"]} / {key}')
                if header['data_offset'] + header['data_bytes'] != r['bytes']:
                    raise ValueError(f'Data length mismatch: {r["archive_member"]}')
                rows.append({'dataset': dataset['id'], **r})
    print(json.dumps({'ok': True, 'records': rows, 'wav_headers_checked': len(rows),
                      'payload_decompressed_fully': False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
