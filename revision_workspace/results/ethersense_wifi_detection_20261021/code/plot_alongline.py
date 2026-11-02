"""Plot only the measured CSVs; whiskers are within-file quantiles, not CIs."""
import csv,json,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# Use the bundled demo-free local paperplot.py style helper.
import paperplot as pp

BASE=Path(__file__).resolve().parents[1]
def read(name):
    with open(BASE/'analysis/alongline'/name,encoding='utf-8-sig') as f:return list(csv.DictReader(f))
rows=read('measured_positions.csv');features=read('fixed_feature_tracking.csv')
ids=list(dict.fromkeys(r['feature_id'] for r in features))
x=np.array([float(r['position_m']) for r in rows]);y=np.array([float(r['power_central_10mhz_db_digital']) for r in rows])
lo=np.array([float(r['within_file_power_q10_db']) for r in rows]);hi=np.array([float(r['within_file_power_q90_db']) for r in rows])
matrix=np.array([[float(next(r for r in features if r['feature_id']==fid and r['record_id']==row['record_id'])['local_floor_contrast_db']) for row in rows] for fid in ids])
retained=np.array([[next(r for r in features if r['feature_id']==fid and r['record_id']==row['record_id'])['feature_retained_at_6db_rule']=='True' for row in rows] for fid in ids])
fig,axes=pp.figure('imwut',span='text',width=452.295/72.27,height=2.65,ncols=2,base=8)
ax=axes[0]
ax.vlines(x,lo,hi,color='#0072B2',lw=1)
ax.scatter(x,y,color='#0072B2',marker='o',s=17,zorder=3)
ax.set_xlabel('Position along supply line (m)');ax.set_ylabel('Central 10 MHz digital power (dB)')
ax.set_title('(a) Level varies with position',loc='left');ax.set_xticks(x);ax.set_ylim(-41,-24)
ax.grid(axis='y',color='.9',lw=.5)
ax=axes[1]
image=ax.imshow(matrix,aspect='auto',origin='upper',cmap='cividis',vmin=0,vmax=28)
for i in range(len(ids)):
    for j in range(len(rows)):
        ax.text(j,i,str(int(retained[i,j])),ha='center',va='center',fontsize=8,
                color='white' if matrix[i,j]<14 else 'black')
ax.set_xticks(np.arange(len(rows)),[str(int(v)) for v in x]);ax.set_yticks(np.arange(len(ids)),ids)
ax.set_xlabel('Position along supply line (m)');ax.set_title('(b) Fixed 1 m spectral references',loc='left')
bar=fig.colorbar(image,ax=ax,shrink=.86,pad=.03);bar.set_label('Peak / local floor (dB)')
pp.save(fig,str(BASE/'figures/D10_alongline_features'))
(BASE/'analysis/alongline/figure_source.json').write_text(json.dumps({'sources':['measured_positions.csv','fixed_feature_tracking.csv'],
    'whiskers':'10th--90th percentile of 16 within-file temporal PSD bins; no independent-repeat CI',
    'cells':'1 = local contrast and enhancement relative to the preceding base both >=6 dB; 0 otherwise',
    'template':'Four B01 peaks frozen across all positions; base is not a verified OFF state',
    'printed_width_in':452.295/72.27},indent=2),encoding='utf-8')
