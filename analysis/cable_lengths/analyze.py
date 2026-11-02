import os
os.environ.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',NUMEXPR_NUM_THREADS='4')
import sys,json,zipfile,struct,hashlib,time,csv
from pathlib import Path
import numpy as np
from scipy import fft,signal,ndimage
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
try:
 import psutil
 psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception: pass
BASE=Path(__file__).resolve().parents[1]; BASE.mkdir(exist_ok=True,parents=True)
N=65536; H=N//2; FS=20000000; FC=20000000
win=signal.windows.hann(N,sym=False).astype(np.float32); scale=FS*float(np.sum(win.astype(float)**2))
freq=fft.fftshift(fft.fftfreq(N,1/FS)); step=FS/N
rows=[]; specs=[]; timespec=[]; histograms=[]; checks=[]
def header(f):
 h=f.read(12); assert h[:4] in (b'RF64',b'RIFF') and h[8:]==b'WAVE'
 dsize=None; fmt=None; pos=12
 while True:
  b=f.read(8); assert len(b)==8
  tag,size=struct.unpack('<4sI',b); pos+=8
  if tag==b'data':
   size=dsize if size==0xffffffff else size
   return fmt,size,pos
  data=f.read(size); pos+=size
  if size%2: f.read(1); pos+=1
  if tag==b'ds64': dsize=struct.unpack_from('<Q',data,8)[0]
  if tag==b'fmt ': fmt=struct.unpack_from('<HHIIHH',data)
with zipfile.ZipFile(sys.argv[1]) as z:
 entries=sorted([x for x in z.infolist() if x.filename.lower().endswith('.wav')],key=lambda x:x.filename)
 assert len(entries)==4
 for idx,ent in enumerate(entries,1):
  started=time.time()
  with z.open(ent) as f:
   fmt,ds,offset=header(f)
   assert fmt==(1,2,FS,FS*2,2,8),fmt
   if ds==0:
    print('EMPTY',ent.filename,flush=True);continue
   nf=ds//2; acc=np.zeros(N); tacc=np.zeros((16,N)); tc=np.zeros(16,dtype=int)
   hist=np.zeros((2,256),dtype=np.int64); sums=np.zeros(2); squares=np.zeros(2); sha=hashlib.sha256()
   carry=np.zeros(0,np.complex64); consumed=0; frames_seen=0; windows=0; firstcheck=None
   remain=ds
   while remain:
    b=f.read(min(remain,2*H*128)); assert len(b)>0; remain-=len(b); sha.update(b)
    raw=np.frombuffer(b,np.uint8).reshape(-1,2)
    for c in range(2): hist[c]+=np.bincount(raw[:,c],minlength=256)
    vals=(raw.astype(np.float32)-128)/128
    sums+=vals.sum(axis=0,dtype=np.float64); squares+=(vals.astype(np.float64)**2).sum(axis=0)
    x=vals[:,0]+1j*vals[:,1]; x=np.concatenate((carry,x))
    if firstcheck is None:
     ff,pp=signal.welch(x[:N*3],fs=FS,window=win,nperseg=N,noverlap=H,return_onesided=False,detrend='constant')
     frames=np.lib.stride_tricks.sliding_window_view(x[:N*3],N)[::H].copy(); frames-=frames.mean(axis=1,keepdims=True)
     test=(np.abs(fft.fft(frames*win,axis=1,workers=4))**2).mean(axis=0)/scale
     firstcheck=float(np.max(np.abs(test-pp))/max(float(pp.max()),1e-30))
    count=max(0,(len(x)-N)//H+1)
    if count:
     frames=np.lib.stride_tricks.sliding_window_view(x,N)[::H][:count].copy(); frames-=frames.mean(axis=1,keepdims=True)
     ft=fft.fft(frames*win,axis=1,workers=4); ps=(ft.real*ft.real+ft.imag*ft.imag)/scale
     acc+=ps.sum(axis=0,dtype=np.float64)
     groups=np.minimum(15,((consumed+np.arange(count)*H+N/2)/nf*16).astype(int))
     for g in np.unique(groups):
      select=groups==g; tacc[g]+=ps[select].sum(axis=0,dtype=np.float64); tc[g]+=select.sum()
     used=count*H; carry=x[used:].copy(); consumed+=used; windows+=count
    else: carry=x
    frames_seen+=len(raw)
   assert frames_seen==nf
   f.read() # triggers final ZIP CRC check
  avg=fft.fftshift(acc/windows); tp=fft.fftshift(tacc/np.maximum(tc[:,None],1),axes=1)
  specs.append(avg); timespec.append(tp); histograms.append(hist)
  rawpower=float(squares.sum()/nf); var=float((squares/nf-(sums/nf)**2).sum())
  mid=(np.abs(freq)<5e6)&(np.abs(freq)>5e3); clean=(np.abs(freq)>5e3)&(np.abs(freq)<9.95e6)
  floor=float(np.median(avg[clean])); sub=float(avg[mid].sum()*step)
  row=dict(id=idx,condition='length_unconfirmed',file=ent.filename,bytes=ent.file_size,data_bytes=ds,frames=nf,duration_s=nf/FS,fs_hz=FS,fc_filename_hz=FC,windows=windows,power_db=10*np.log10(rawpower),ac_power_db=10*np.log10(var),welch_power_db=10*np.log10(avg.sum()*step),central10mhz_db=10*np.log10(sub),median_psd_db_hz=10*np.log10(floor),I_codes=int(np.count_nonzero(hist[0])),Q_codes=int(np.count_nonzero(hist[1])),I_min=int(np.flatnonzero(hist[0])[0]),I_max=int(np.flatnonzero(hist[0])[-1]),Q_min=int(np.flatnonzero(hist[1])[0]),Q_max=int(np.flatnonzero(hist[1])[-1]),I_center_pct=100*hist[0,128]/nf,Q_center_pct=100*hist[1,128]/nf,rail_pct=100*hist[:,[0,255]].sum()/(nf*2),pcm_sha256=sha.hexdigest(),scipy_relative_error=firstcheck,zip_crc_ok=True)
  rows.append(row)
  print(json.dumps(row),flush=True); print('seconds',round(time.time()-started,1),flush=True)
np.savez_compressed(BASE/'spectra.npz',frequency_offset_hz=freq,psd=specs,time_psd=timespec,histograms=histograms)
with open(BASE/'record_metrics.csv','w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

(BASE/'processing_complete.json').write_text(json.dumps({'valid_records':len(rows),'empty_records':len(entries)-len(rows),'settings':{'nfft':N,'overlap':H,'frequency_bin_hz':step,'enbw_hz':1.5*step}},indent=2),encoding='utf8')
