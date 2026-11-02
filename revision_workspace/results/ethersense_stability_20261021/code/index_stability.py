"""Index headers only; map dates using the user's explicit filename confirmation."""
import csv, hashlib, json, os, struct, zipfile
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[1]
ARCHIVE=ROOT/'attachments/稳定性测试2026_10_21.zip'
REMOTE=os.environ.get('ETHERSENSE_STABILITY_REMOTE','/tmp/ethersense_stability_20261021')
records=[]
with zipfile.ZipFile(ARCHIVE) as z:
    for i in z.infolist():
        if not i.filename.lower().endswith('.wav'):continue
        name=i.filename.rsplit('/',1)[-1]
        month,day=map(int,Path(name).stem.split('.'))
        date=f'2026-{month:02d}-{day:02d}'
        with z.open(i) as f:h=f.read(4096)
        pos=12;ds=None;fmt=None
        while pos+8<=len(h):
            cid=h[pos:pos+4];size=struct.unpack('<I',h[pos+4:pos+8])[0]
            if cid==b'ds64':ds=struct.unpack('<QQQ',h[pos+8:pos+32])
            if cid==b'fmt ':fmt=struct.unpack('<HHIIHH',h[pos+8:pos+24])
            if cid==b'data':break
            pos+=8+size+(size&1)
        else:raise ValueError('Missing data chunk')
        size=ds[1] if size==0xffffffff else size
        assert fmt[0]==1 and fmt[1]==2 and fmt[2]==20_000_000 and fmt[5]==8
        assert pos+8+size==i.file_size
        records.append(dict(record_id='ST_'+date.replace('-',''),file_name=name,archive_member=i.filename,
            date=date,day=day,state='on',state_source='User identifies the complete archive as heater 2 stability recordings; no off/background file is labeled.',
            center_frequency_hz=20_000_000,center_frequency_source='User: promised heater-2 series centered at 20 MHz.',
            date_source='User explicitly confirms filenames are actual measurement dates; year 2026 from supplied archive.',
            crc32_expected=f'{i.CRC:08x}',file_size_bytes=i.file_size,format_tag=fmt[0],channels=fmt[1],
            sample_rate_hz=fmt[2],block_align=fmt[4],bits_per_sample=fmt[5],data_offset=pos+8,data_bytes=size,
            sample_frames=size//fmt[4],rf64_sample_frames=ds[2],duration_s=size/fmt[4]/fmt[2]))
records.sort(key=lambda r:r['date'])
inv=dict(archive=str(ARCHIVE.resolve()),original_hugo_path='Desktop/ubicomp/新建文件夹/IQ/2026_10_21.zip',
    archive_bytes=ARCHIVE.stat().st_size,archive_sha256=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
    record_count=len(records),expanded_bytes=sum(r['file_size_bytes'] for r in records),records=records)
(OUT/'inventory.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'jobs.json').write_text(json.dumps([dict(dataset='stability_20mhz',record_id=r['record_id'],archive=REMOTE+'/data.zip',member=r['archive_member']) for r in records]),encoding='utf-8')
with (OUT/'daymap.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['file','day','date','state','note']);w.writeheader()
    w.writerows(dict(file=r['file_name'],day=r['day'],date=r['date'],state=r['state'],note=r['date_source']) for r in records)
print(json.dumps({'records':len(records),'date_range':[records[0]['date'],records[-1]['date']],
 'seconds':[min(r['duration_s'] for r in records),max(r['duration_s'] for r in records)],'expanded_bytes':inv['expanded_bytes']},ensure_ascii=False))
