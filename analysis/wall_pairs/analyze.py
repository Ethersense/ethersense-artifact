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
N=65536; H=N//2; FS=20000000; FC=20038000
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
 assert len(entries)==6
 for idx,ent in enumerate(entries,1):
  started=time.time()
  with z.open(ent) as f:
   fmt,ds,offset=header(f)
   assert fmt==(1,2,FS,FS*2,2,8),fmt
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
  row=dict(id=idx,condition='no_wall' if idx%2 else 'wall',pair=(idx+1)//2,file=ent.filename,bytes=ent.file_size,data_bytes=ds,frames=nf,duration_s=nf/FS,fs_hz=FS,fc_filename_hz=FC,windows=windows,power_db=10*np.log10(rawpower),ac_power_db=10*np.log10(var),welch_power_db=10*np.log10(avg.sum()*step),central10mhz_db=10*np.log10(sub),median_psd_db_hz=10*np.log10(floor),I_codes=int(np.count_nonzero(hist[0])),Q_codes=int(np.count_nonzero(hist[1])),I_min=int(np.flatnonzero(hist[0])[0]),I_max=int(np.flatnonzero(hist[0])[-1]),Q_min=int(np.flatnonzero(hist[1])[0]),Q_max=int(np.flatnonzero(hist[1])[-1]),I_center_pct=100*hist[0,128]/nf,Q_center_pct=100*hist[1,128]/nf,rail_pct=100*hist[:,[0,255]].sum()/(nf*2),pcm_sha256=sha.hexdigest(),scipy_relative_error=firstcheck,zip_crc_ok=True)
  rows.append(row)
  print(json.dumps(row),flush=True); print('seconds',round(time.time()-started,1),flush=True)
np.savez_compressed(BASE/'spectra.npz',frequency_offset_hz=freq,psd=specs,time_psd=timespec,histograms=histograms)
with open(BASE/'record_metrics.csv','w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
P=np.array(specs); L=10*np.log10(np.maximum(P,1e-30)); local=L-ndimage.median_filter(L,size=(1,201),mode='nearest')
valid=(np.abs(freq)>5e3)&(np.abs(freq)<9.95e6)
pks,_=signal.find_peaks(local[0],height=6,prominence=3,distance=6)
pks=pks[valid[pks]]; pks=pks[np.argsort(local[0,pks])[::-1]][:24]; pks=np.sort(pks)
peakrows=[]
for k in pks:
 r={'reference_offset_hz':freq[k],'reference_contrast_db':local[0,k]}
 for i in range(6):
  lo=max(1,k-16);hi=min(N-1,k+17); pk,_=signal.find_peaks(L[i,lo-1:hi+1]); pk=pk+lo-1; pk=pk[(pk>=lo)&(pk<hi)]
  if len(pk):
   best=pk[np.argmax(local[i,pk])];r[f'r{i+1}_offset_hz']=freq[best];r[f'r{i+1}_contrast_db']=local[i,best];r[f'r{i+1}_peak_psd_db_hz']=L[i,best]
  else:r[f'r{i+1}_offset_hz']=None;r[f'r{i+1}_contrast_db']=None;r[f'r{i+1}_peak_psd_db_hz']=None
 peakrows.append(r)
if peakrows:
 with open(BASE/'reference_peak_tracking.csv','w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=peakrows[0]);w.writeheader();w.writerows(peakrows)
pairs=[]
for j in range(3):
 a,b=2*j,2*j+1
 r=dict(pair=j+1,wall_minus_no_wall_full_db=rows[b]['power_db']-rows[a]['power_db'],wall_minus_no_wall_central10_db=rows[b]['central10mhz_db']-rows[a]['central10mhz_db'],median_bin_change_db=float(np.median(L[b,valid]-L[a,valid])),logpsd_corr=float(np.corrcoef(L[a,valid],L[b,valid])[0,1]),local_contrast_corr=float(np.corrcoef(local[a,valid],local[b,valid])[0,1]),reference_candidates=len(pks),no_wall_matches_6db=sum((p.get(f'r{a+1}_contrast_db') or -999)>=6 for p in peakrows),wall_matches_6db=sum((p.get(f'r{b+1}_contrast_db') or -999)>=6 for p in peakrows))
 pairs.append(r)
# Time blocks are diagnostics, not independent replicates.
tr=[]
for i in range(6):
 for g in range(16):
  v=timespec[i][g];tr.append(dict(id=i+1,block=g+1,center_time_s=(g+.5)/16*rows[i]['duration_s'],ac_power_db=10*np.log10(v.sum()*step)))
with open(BASE/'time_blocks.csv','w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=tr[0]);w.writeheader();w.writerows(tr)
summary={'records':rows,'pairs':pairs,'settings':{'nfft':N,'overlap':H,'frequency_bin_hz':step,'enbw_hz':1.5*step,'psd':'two-sided complex I+jQ, Hann, per-window mean removal','scale':'digital amplitude normalized by 128; no dBm calibration','reference':'strongest up to 24 local peaks in recording 1 only; +/-4.883 kHz tracking; 6 dB local contrast','IQ_convention':'unconfirmed; RF candidates fc+offset and fc-offset'},'cross_record_logpsd_corr':np.corrcoef(L[:,valid]).tolist()}
(BASE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=lambda x: x.item()),encoding='utf8')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
colors=['#1261a0','#c04b27']
fig,axs=plt.subplots(3,1,figsize=(11,9),sharex=True,sharey=True)
for j,ax in enumerate(axs):
 for i in range(2):ax.plot(freq/1e6,L[2*j+i],lw=.65,color=colors[i],alpha=.85,label=f'{2*j+i+1}: '+('No wall' if i==0 else 'Wall'))
 ax.set_ylabel('PSD (dB/Hz, digital)');ax.legend(loc='upper right');ax.grid(alpha=.2);ax.set_title(f'Pair {j+1}: wall - no wall power = {pairs[j]["wall_minus_no_wall_full_db"]:+.2f} dB',loc='left')
axs[-1].set_xlabel('Encoded frequency offset (MHz), I + jQ');fig.tight_layout();fig.savefig(BASE/'paired_spectra.png',dpi=190);fig.savefig(BASE/'paired_spectra.pdf');plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(11,4))
for i in range(6):
 vals=[v for v in tr if v['id']==i+1];axs[0].plot([v['center_time_s'] for v in vals],[v['ac_power_db'] for v in vals],label=str(i+1)+(' NW' if i%2==0 else ' W'),lw=1)
axs[0].set_xlabel('Within-record time (s)');axs[0].set_ylabel('AC power (dB, digital)');axs[0].legend(ncol=3,fontsize=8);axs[0].grid(alpha=.2)
for j in range(3):axs[1].plot([0,1],[rows[2*j]['power_db'],rows[2*j+1]['power_db']],'-o',label=f'Pair {j+1}')
axs[1].set_xticks([0,1],['No wall','Wall']);axs[1].set_ylabel('Full-band power (dB, digital)');axs[1].legend();axs[1].grid(alpha=.2);fig.tight_layout();fig.savefig(BASE/'power_and_stability.png',dpi=190);plt.close(fig)
print('SUMMARY',json.dumps(pairs,default=lambda x:x.item()),flush=True)
