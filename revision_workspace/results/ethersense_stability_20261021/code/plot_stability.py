"""Measured daily stability, actual dates, fixed first-day reference; vector output."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='4'
import csv,json,shutil
from datetime import datetime
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter,DayLocator
OUT=Path(__file__).resolve().parents[1]
F=OUT/'figures';F.mkdir(exist_ok=True)
with open(OUT/'analysis/daily_metrics.csv',encoding='utf-8-sig') as source_csv:
    rows=list(csv.DictReader(source_csv))
dates=[datetime.fromisoformat(r['date']) for r in rows]
nref=int(rows[0]['day1_candidates'])
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.labelsize':8,'axes.titlesize':8,
 'xtick.labelsize':8.1,'ytick.labelsize':8.1,'pdf.fonttype':42,'ps.fonttype':42,
 'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,2,figsize=(452.295/72.27,3.85),sharex=True)
fig.subplots_adjust(left=.115,right=.975,bottom=.14,top=.91,hspace=.55,wspace=.40)
configs=[('full_power_db','Full-band digital power (dB)','(a) Received level','#0072B2',None),
 ('comb_khz','Comb spacing (kHz)','(b) Harmonic spacing','#D55E00',None),
 ('day1_log_psd_correlation','Correlation with Day 1','(c) Full log spectrum','#009E73',(0,1.03)),
 ('retained_candidates','Retained Day-1 peaks',f'(d) Fixed {nref}-peak reference','#CC79A7',(0,nref+1))]
for ax,(key,label,title,color,ylim) in zip(axes.ravel(),configs):
    vals=np.array([float(r[key]) for r in rows]);ax.plot(dates,vals,'o-',ms=3,lw=1.1,color=color)
    ax.set_ylabel(label);ax.set_title(title,loc='left',pad=5)
    if ylim:ax.set_ylim(*ylim)
    else:
        span=max(np.ptp(vals),.1);ax.set_ylim(vals.min()-.35*span,vals.max()+.35*span)
    ax.grid(axis='y',color='.9',lw=.5)
    ax.xaxis.set_major_locator(DayLocator(interval=3));ax.xaxis.set_major_formatter(DateFormatter('%m-%d'))
    if key=='retained_candidates':ax.set_yticks(np.linspace(0,nref,5))
    elif key=='day1_log_psd_correlation':ax.set_yticks([0,.5,1])
for ax in axes[-1]:ax.set_xlabel('Measurement date (2026)')
fig.canvas.draw();renderer=fig.canvas.get_renderer();W,H=fig.canvas.get_width_height()
texts=[t for ax in axes.ravel() for t in [ax.title,ax.xaxis.label,ax.yaxis.label,*ax.get_xticklabels(),*ax.get_yticklabels()] if t.get_visible() and t.get_text()]
outside=[t.get_text() for t in texts if (lambda b:b.x0<-.5 or b.y0<-.5 or b.x1>W+.5 or b.y1>H+.5)(t.get_window_extent(renderer))]
if outside:raise RuntimeError('Text outside canvas: '+repr(outside))
for ext in ['pdf','png']:fig.savefig(F/('D7_daily_stability.'+ext),dpi=300)
(OUT/'analysis/figure_qa.json').write_text(json.dumps({'outside_canvas':outside,'data_source':'analysis/daily_metrics.csv',
    'dates':[r['date'] for r in rows],'threshold_fit':'Day 1 only; no subsequent-day tuning','positive_only':True,
    'line_connects':'Segments connect successive measured dates; uncertainty is not estimated.'},indent=2),encoding='utf-8')
print('D7 generated from all 12 daily recordings.')
