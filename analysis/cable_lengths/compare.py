import os
os.environ.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
import json,csv,zipfile
from pathlib import Path
import numpy as np
from scipy import signal,ndimage
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
try:
 import psutil
 psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception: pass
B=Path(__file__).resolve().parents[1]
rows=list(csv.DictReader((B/'record_metrics.csv').open(encoding='utf-8-sig')))
a=np.load(B/'spectra.npz');f=a['frequency_offset_hz'];P=a['psd'];T=a['time_psd'];df=f[1]-f[0];n=len(rows)
L=10*np.log10(np.maximum(P,1e-30));C=L-ndimage.median_filter(L,size=(1,201),mode='nearest');valid=(np.abs(f)>5000)&(np.abs(f)<9.95e6)
peaks=[]
for i in range(n):
 p,_=signal.find_peaks(C[i],height=6,prominence=3,distance=8);p=p[valid[p]];p=p[np.argsort(C[i,p])[::-1]][:40];peaks.append(np.sort(p))
ref=peaks[0];track=[]
for k in ref:
 r={'reference_offset_hz':float(f[k])}
 for i in range(n):
  lo=max(1,k-4);hi=min(len(f)-2,k+4);q,_=signal.find_peaks(L[i,lo-1:hi+2]);q=q+lo-1;q=q[(q>=lo)&(q<=hi)]
  if len(q):
   q=q[np.argmax(C[i,q])];r.update({f'r{i+1}_offset_hz':float(f[q]),f'r{i+1}_contrast_db':float(C[i,q]),f'r{i+1}_peak_db_hz':float(L[i,q])})
  else:r.update({f'r{i+1}_offset_hz':None,f'r{i+1}_contrast_db':None,f'r{i+1}_peak_db_hz':None})
 track.append(r)
with (B/'peak_tracking.csv').open('w',newline='',encoding='utf-8-sig') as out:
 w=csv.DictWriter(out,fieldnames=track[0]);w.writeheader();w.writerows(track)
comparisons=[]
for i in range(n):
 tr=[r for r in track if r[f'r{i+1}_contrast_db'] is not None and r[f'r{i+1}_contrast_db']>=6]
 deltas=[r[f'r{i+1}_peak_db_hz']-r['r1_peak_db_hz'] for r in tr]
 shifts=[abs(r[f'r{i+1}_offset_hz']-r['r1_offset_hz']) for r in tr]
 comparisons.append(dict(id=i+1,reference_peak_count=len(ref),visible_reference_peaks=len(tr),median_peak_change_db=float(np.median(deltas)) if deltas else None,max_peak_shift_hz=max(shifts) if shifts else None,ac_power_change_db=float(rows[i]['ac_power_db'])-float(rows[0]['ac_power_db']),logpsd_corr=float(np.corrcoef(L[0,valid],L[i,valid])[0,1]),local_contrast_corr=float(np.corrcoef(C[0,valid],C[i,valid])[0,1]),within_record_ac_span_db=float(np.ptp(10*np.log10(T[i].sum(axis=1)*df)))))
summary={'comparisons_to_record_1':comparisons,'logpsd_corr':np.corrcoef(L[:,valid]).tolist(),'local_contrast_corr':np.corrcoef(C[:,valid]).tolist(),'top_peaks':[{'id':i+1,'offset_khz':(f[p]/1000).tolist(),'contrast_db':C[i,p].tolist()} for i,p in enumerate(peaks)],'mapping':'awaiting author confirmation; no lengths assigned','reference_method':'up to 40 strongest peaks in recording 1, local contrast >=6dB, prominence >=3dB, tracking +/-4 bins = 1.221kHz; selected after viewing this batch; not identification'}
(B/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
colors=plt.get_cmap('tab10').colors
fig,axs=plt.subplots(2,1,figsize=(12,8))
zoom_center=float(np.median(f[ref])); zoom_mask=np.abs(f-zoom_center)<300000
for i in range(n):
 label=f'{i+1}: {rows[i]["file"].split("_")[0]}'
 for ax,mask in [(axs[0],np.ones(len(f),bool)),(axs[1],zoom_mask)]:ax.plot(f[mask]/1e6,L[i,mask],label=label,lw=.7,alpha=.8,color=colors[i])
for ax in axs:ax.set_ylabel('PSD (dB/Hz, digital)');ax.grid(alpha=.2);ax.legend(ncol=3,fontsize=8)
axs[0].set_title('Cable-length batch: recording labels pending confirmation',loc='left');axs[1].set_xlabel('Encoded frequency offset (MHz), channel 1 + j channel 2');fig.tight_layout();fig.savefig(B/'spectra_comparison.png',dpi=180);fig.savefig(B/'spectra_comparison.pdf');plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(11,4))
for i in range(n):axs[0].plot((np.arange(16)+.5)/16*float(rows[i]['duration_s']),10*np.log10(T[i].sum(axis=1)*df),'-o',ms=2,label=f'{i+1}',color=colors[i])
axs[0].set_xlabel('Time within recording (s)');axs[0].set_ylabel('AC power (dB, digital)');axs[0].legend();axs[0].grid(alpha=.2)
im=axs[1].imshow(summary['local_contrast_corr'],vmin=0,vmax=1,cmap='Blues');axs[1].set_xticks(range(n),range(1,n+1));axs[1].set_yticks(range(n),range(1,n+1));axs[1].set_title('Local spectral-contrast correlation')
for i in range(n):
 for j in range(n):axs[1].text(j,i,f'{summary["local_contrast_corr"][i][j]:.2f}',ha='center',va='center',color='white' if summary['local_contrast_corr'][i][j]>.65 else 'black')
fig.colorbar(im,ax=axs[1]);fig.tight_layout();fig.savefig(B/'stability_and_similarity.png',dpi=180);plt.close(fig)
print(json.dumps(summary['comparisons_to_record_1'],ensure_ascii=False))
print('TOP_POSITIVE_KHZ',[(i+1,sorted((round(float(f[k]/1000),3),round(float(C[i,k]),1)) for k in peaks[i] if 5000<f[k]<1e6)) for i in range(n)])
