"""Real-data K4 paper figures. Run analyze_k4.py first; no generated observations.

The current acmlarge manuscript has a 6.2584-inch text width. Only the
paperplot style is reused. Every result is read from raw-derived NPZ/CSV files.
Full-spectrum display uses peak-preserving blocks of eight FFT bins; all
statistics and peak zooms retain the original 305.18 Hz grid.
"""
from __future__ import annotations
import csv
import hashlib
import json
import runtime_limits
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import paperplot as pp

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'paper/figures'
WIDTH=8.5-162/72.27
COLORS=['#0072B2','#D55E00','#009E73','#CC79A7']
MARKERS=['o','s','^','D','v','P','X','>']
LINES=['-','--',':','-.']


def rows(name):
    with (ROOT/name).open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))


def number(row,key):
    value=row.get(key,'')
    return float(value) if value not in ('',None) else np.nan


def thin(x,y,block=8):
    n=len(x)//block*block
    return x[:n].reshape(-1,block).mean(axis=1),np.max(y[:n].reshape(-1,block),axis=1)


def make(height=3,nrows=1,ncols=1,**kw):
    fig,axes=pp.figure('imwut',span='text',width=WIDTH,height=height,nrows=nrows,ncols=ncols,base=9,**kw)
    matplotlib.rcParams['savefig.bbox']=None
    return fig,axes


def save(fig,name,sources,note):
    fig.canvas.draw()
    # Keep the actual print size, independent of labels or the tight-bbox default.
    fig.savefig(OUT/(name+'.pdf'),bbox_inches=None)
    fig.savefig(OUT/(name+'.png'),dpi=600,bbox_inches=None)
    texts=[t.get_fontsize() for t in fig.findobj(matplotlib.text.Text) if t.get_visible() and t.get_text()]
    meta={'figure':name,'width_inches':float(fig.get_size_inches()[0]),'height_inches':float(fig.get_size_inches()[1]),
          'min_font_size_pt':min(texts),'png_dpi':600,'sources':sources,'script':'code/plot_k4.py','note':note}
    provenance.append(meta);plt.close(fig)


def matrix(ids,group,field):
    m=np.eye(len(ids));lookup={rid:i for i,rid in enumerate(ids)}
    for r in pairs:
        if r['group']==group and r['record_a'] in lookup and r['record_b'] in lookup:
            i,j=lookup[r['record_a']],lookup[r['record_b']];m[i,j]=m[j,i]=number(r,field)
    return m


def heat(ax,m,labels,title,annotate=False):
    im=ax.pcolormesh(np.arange(len(labels)+1)-.5,np.arange(len(labels)+1)-.5,m,vmin=-1,vmax=1,cmap='RdBu_r',shading='flat')
    ax.set_aspect('equal');ax.invert_yaxis()
    ax.set_xticks(range(len(labels)),labels=labels,rotation=90)
    ax.set_yticks(range(len(labels)),labels=labels);ax.set_title(title);ax.grid(False)
    if annotate:
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j,i,f'{m[i,j]:.2f}',ha='center',va='center',fontsize=8,
                        color='white' if abs(m[i,j])>.65 else 'black')
    return im


def offset_label(center): return f'Encoded frequency offset (MHz); center = {center:g} MHz'


def main():
    global provenance,pairs
    OUT.mkdir(parents=True,exist_ok=True);provenance=[]
    summary=json.loads((ROOT/'analysis_summary.json').read_text(encoding='utf-8'))
    inv=json.loads((ROOT/'data_inventory.json').read_text(encoding='utf-8'))
    index={r['record_id']:r for r in inv['records']}
    metrics=rows('record_metrics.csv');met={r['record_id']:r for r in metrics}
    tracking=rows('feature_tracking.csv');defs=rows('feature_definitions.csv');pairs=rows('pairwise_similarity.csv')
    arrays=np.load(ROOT/'derived_spectra.npz')
    def get(rid,key): return arrays[rid+'__'+key]
    stable=summary['stability']['record_ids'];main_ids=summary['cable']['main_record_ids']
    dated=summary['stability']['confirmed_date_count']==len(stable) and len(stable)>0
    stable_labels=[index[rid]['acquisition_date'] if dated else rid for rid in stable]
    xlabel='Acquisition date' if dated else 'Recording ID (calendar dates unconfirmed)'
    all_stable_dates=summary['stability']['confirmed_calendar_dates']
    tdefs=[r for r in defs if r['experiment']=='stability']
    wdefs=[r for r in defs if r['experiment']=='cable']

    # K4-1: entire acquired bandwidth, plus a declared first-reference candidate.
    fig,axes=make(4.5,nrows=2)
    for j,rid in enumerate(stable):
        x,y=thin(get(rid,'f')/1e6,get(rid,'psd_db'))
        axes[0].plot(x,y,color=COLORS[j%4],ls=LINES[j//4%4],marker=MARKERS[j%4],markevery=1300,ms=2.6,lw=.8,label=rid)
    axes[0].set(xlim=(-10,10),xlabel=offset_label(1587),ylabel='PSD (dB digital unit²/Hz)',title='(a) Entire 20 MHz capture')
    axes[0].legend(ncol=5,loc='upper center',bbox_to_anchor=(.5,1.36),fontsize=8)
    if tdefs:
        f0=number(tdefs[0],'reference_offset_hz')
        for j,rid in enumerate(stable):
            f=get(rid,'f');mask=np.abs(f-f0)<=15000
            axes[1].plot((f[mask]-f0)/1e3,get(rid,'psd_db')[mask],color=COLORS[j%4],ls=LINES[j//4%4],marker=MARKERS[j%4],markevery=23,ms=2.6,lw=.9)
        axes[1].set(xlabel=f'Offset from TF01 reference ({f0/1e6:+.6f} MHz), kHz',ylabel='PSD (dB digital unit²/Hz)',title='(b) TF01: first-reference candidate, attribution unverified')
    save(fig,'K4-1_stability_spectra',['derived_spectra.npz','feature_definitions.csv'],
         f'{len(stable)} recordings, {len(all_stable_dates)} confirmed calendar dates. Entire 20 MHz shown; encoded offset avoids inventing I/Q orientation. Narrow-peak zoom uses original FFT bins.')

    # K4-2: frequency, relative amplitude, local contrast, power/noise.
    fig,axes=make(5.0,nrows=2,ncols=2)
    x=np.arange(len(stable));tmap={(r['record_id'],r['feature_id']):r for r in tracking if r['experiment']=='stability'}
    for j,definition in enumerate(tdefs[:4]):
        fid=definition['feature_id'];rs=[tmap.get((rid,fid),{}) for rid in stable]
        for ax,key in ((axes[0,0],'frequency_shift_hz_if_detected'),(axes[0,1],'relative_peak_amplitude_db'),(axes[1,0],'local_floor_contrast_db')):
            vals=np.array([number(r,key) for r in rs])
            if key=='frequency_shift_hz_if_detected': vals/=1000
            ax.plot(x,vals,color=COLORS[j],marker=MARKERS[j],ms=3,ls=LINES[j],label=fid)
    axes[0,0].set(ylabel='Peak displacement (kHz)',title='(a) Detected peaks only')
    axes[0,1].set(ylabel='Relative peak PSD (dB)',title='(b) Relative to strongest bank peak')
    axes[1,0].set(ylabel='Peak / local median (dB)',title='(c) Local spectral contrast');axes[1,0].axhline(6,color='#555555',lw=.7,ls=':')
    p=np.array([number(met[rid],'full_band_power_db') for rid in stable])
    floor=np.array([number(met[rid],'local_noise_floor_median_db_per_hz') for rid in stable])
    axes[1,1].plot(x,p-p[0],marker='o',color=COLORS[0],label='Full-band power shift')
    axes[1,1].plot(x,floor-floor[0],marker='s',ls='--',color=COLORS[1],label='Local-floor shift')
    axes[1,1].set(ylabel='Change from first record (dB)',title='(d) Digital level / background proxy')
    axes[0,0].legend(ncol=2,fontsize=8);axes[1,1].legend(fontsize=8)
    for ax in axes.flat:
        ax.set_xticks(x,stable_labels,rotation=50 if dated else 0);ax.set_xlabel(xlabel)
    save(fig,'K4-2_peak_variation',['feature_tracking.csv','record_metrics.csv'],
         'Up to four of eight prespecified-reference candidates are shown; complete results remain in CSV. Missing detections are gaps; no invented zero drift.')

    # K4-3: recordings or confirmed daily averages, with common correlation scale.
    daily=summary['stability'].get('daily_analysis',{})
    if len(daily.get('dates',[]))>=2:
        labels=daily['dates'];pd=arrays['daily_psd_db'];pc=arrays['daily_local_contrast']
        axis=arrays['daily_axis_hz'];guard=(np.abs(axis)>5000) if daily['axis_kind']=='encoded_offset_hz' else np.abs(axis-1587e6)>5000
        m1=np.corrcoef(pd[:,guard]);m2=np.corrcoef(pc[:,guard]);unit='Confirmed daily means'
    else:
        labels=stable;m1=matrix(stable,'stability','log_psd_correlation');m2=matrix(stable,'stability','local_contrast_correlation');unit='Recordings; dates unconfirmed'
    fig,axes=make(3.7,ncols=2)
    im=heat(axes[0],m1,labels,'(a) Log-PSD correlation')
    heat(axes[1],m2,labels,'(b) Local-contrast correlation')
    cb=fig.colorbar(im,ax=list(axes),shrink=.79,label='Pearson r',ticks=[-1,-.5,0,.5,1],pad=.02)
    cb.solids.set_rasterized(False)
    fig.suptitle(unit,fontsize=9)
    save(fig,'K4-3_fingerprint_similarity',['pairwise_similarity.csv','derived_spectra.npz','verified_daily_pairwise_similarity.csv'],
         'Pair correlations are descriptive and not independent samples. No cross-experiment correlation or multi-class accuracy is computed.')

    # K4-4: all four technical repeats in each cell, mean in linear PSD units.
    fig,axes=make(4.3,nrows=2,sharex=True)
    for ax,distance in zip(axes,(40,80)):
        for j,g in enumerate(('c','s')):
            ids=[rid for rid in main_ids if index[rid]['geometry']==g and index[rid]['distance_label_cm']==distance]
            f=get(ids[0],'f')/1e6;ps=np.array([get(rid,'psd') for rid in ids]);dbs=10*np.log10(np.maximum(ps,np.finfo(float).tiny))
            xx,yy=thin(f,10*np.log10(ps.mean(axis=0)));_,lo=thin(f,dbs.min(axis=0));_,hi=thin(f,dbs.max(axis=0))
            ax.fill_between(xx,lo,hi,color=COLORS[j],alpha=.15,lw=0)
            ax.plot(xx,yy,color=COLORS[j],ls=LINES[j],lw=1,label=f'{g.upper()}: mean; range of 4 repeats')
        ax.set(xlim=(-10,10),ylabel='PSD (dB digital unit²/Hz)',title=f'{distance} cm distance label')
        ax.legend(loc='upper center',bbox_to_anchor=(.5,1.05),fontsize=8)
    axes[-1].set_xlabel(offset_label(20))
    save(fig,'K4-4_curved_straight_spectra',['derived_spectra.npz','data_index.csv'],
         'C=curved, S=straight. Each condition includes all four technical recordings; shading is their range, not an independent-date confidence interval. Full acquired 20 MHz.')

    # K4-5: four recorded values plus mean +/- sample SD, no significance tests.
    fig,axes=make(2.9,ncols=2)
    for ax,field,title,ylabel in zip(axes,('full_band_power_db','fixed_peak_region_to_floor_db'),
            ('(a) Entire 20 MHz','(b) Fixed candidate-frequency regions'),
            ('Band power (dB digital unit²)','Region power / local floor (dB)')):
        for j,g in enumerate(('c','s')):
            means=[];sds=[]
            for k,distance in enumerate((40,80)):
                ids=[rid for rid in main_ids if index[rid]['geometry']==g and index[rid]['distance_label_cm']==distance]
                v=np.array([number(met[rid],field) for rid in ids]);means.append(v.mean());sds.append(v.std(ddof=1));xx=k+(j-.5)*.16
                ax.scatter(xx+np.linspace(-.035,.035,len(v)),v,s=13,facecolors='none',edgecolors=COLORS[j],marker=MARKERS[j],zorder=4)
            ax.errorbar(np.arange(2)+(j-.5)*.16,means,yerr=sds,color=COLORS[j],marker=MARKERS[j],ls=LINES[j],label=g.upper(),capsize=3,lw=1)
        ax.set_xticks([0,1],['40','80']);ax.set(xlabel='Distance label from outlet (cm)',ylabel=ylabel,title=title);ax.legend()
    save(fig,'K4-5_power_factorial',['record_metrics.csv','cable_condition_statistics.csv'],
         'Points are four consecutive technical recordings per condition; error bars are sample SD of log power, not independent-date confidence intervals. Gain/AGC comparability unverified; levels are not calibrated dBm.')

    # K4-6: location repeatability and fingerprint correlation.
    fig,axes=make(3.5,ncols=2,gridspec_kw={'width_ratios':[1,1.15]})
    groups=[('c',40),('s',40),('c',80),('s',80)];labels=['C40','S40','C80','S80']
    for j,d in enumerate(wdefs[:4]):
        xs=[];means=[];lows=[];highs=[]
        for k,(g,dist) in enumerate(groups):
            rr=[r for r in tracking if r['experiment']=='cable' and r['feature_id']==d['feature_id'] and r['geometry']==g and number(r,'distance_label_cm')==dist]
            v=np.array([number(r,'frequency_shift_hz_if_detected')/1000 for r in rr]);v=v[np.isfinite(v)]
            if len(v):
                xs.append(k+(j-1.5)*.12);means.append(v.mean());lows.append(v.mean()-v.min());highs.append(v.max()-v.mean())
        axes[0].errorbar(xs,means,yerr=[lows,highs],marker=MARKERS[j],ls='none',color=COLORS[j],capsize=2,label=d['feature_id'])
    axes[0].set_xticks(range(4),labels,rotation=30);axes[0].set(ylabel='Peak displacement (kHz)',title='(a) Mean and observed range')
    axes[0].legend(ncol=2,loc='upper center',bbox_to_anchor=(.5,1.25),fontsize=8)
    ids=[rid for g,dist in groups for rid in main_ids if index[rid]['geometry']==g and index[rid]['distance_label_cm']==dist]
    m=matrix(ids,'cable_main','local_contrast_correlation')
    im=axes[1].pcolormesh(np.arange(len(ids)+1)-.5,np.arange(len(ids)+1)-.5,m,vmin=-1,vmax=1,cmap='RdBu_r',shading='flat')
    axes[1].set_aspect('equal');axes[1].invert_yaxis()
    axes[1].set_xticks([1.5,5.5,9.5,13.5],labels,rotation=30);axes[1].set_yticks([1.5,5.5,9.5,13.5],labels);axes[1].grid(False)
    for b in (3.5,7.5,11.5): axes[1].axvline(b,color='black',lw=.5);axes[1].axhline(b,color='black',lw=.5)
    axes[1].set_title('(b) All 16 recordings; four per block')
    cb=fig.colorbar(im,ax=axes[1],fraction=.045,pad=.03,label='Local-contrast Pearson r',ticks=[-1,0,1])
    cb.solids.set_rasterized(False)
    save(fig,'K4-6_peak_repeatability',['feature_tracking.csv','pairwise_similarity.csv'],
         'Peak positions shown only when >=6 dB above local median; upper four candidates selected on S40 repeat1, never best-of-four. Every heatmap block includes all four repeats.')

    # Appendix: extra measured distances are not silently discarded or extrapolated.
    fig,axes=make(3.0,ncols=2)
    cable_rows=[r for r in metrics if r['experiment']=='cable']
    for j,g in enumerate(('c','s')):
        distances=sorted({int(r['distance_label_cm']) for r in cable_rows if r['geometry']==g})
        for ax,field in zip(axes,('full_band_power_db','fixed_peak_region_to_floor_db')):
            means=[];sds=[]
            for dist in distances:
                v=[number(r,field) for r in cable_rows if r['geometry']==g and int(r['distance_label_cm'])==dist]
                means.append(np.mean(v));sds.append(np.std(v,ddof=1));ax.scatter(np.full(len(v),dist),v,s=9,marker=MARKERS[j],facecolors='none',edgecolors=COLORS[j])
            ax.errorbar(distances,means,yerr=sds,label=g.upper(),marker=MARKERS[j],color=COLORS[j],ls=LINES[j],lw=1,capsize=2)
            ax.set(xlabel='Distance label from outlet (cm)');ax.legend()
    axes[0].set(ylabel='Full-band power (dB digital unit²)',title='(a) All 48 cable recordings')
    axes[1].set(ylabel='Region power / local floor (dB)',title='(b) Same fixed reference regions')
    save(fig,'K4-S1_all_distances',['record_metrics.csv','metadata_overrides.csv'],
         'Extra distances are exploratory. Original s150cm-4 is grouped at S160 repeat4 per user correction; raw file unchanged. Distance object and acquisition order remain unresolved.')

    fig,axes=make(3.1,ncols=2)
    contrasts=rows('edge_sensitivity_contrasts.csv')
    comparisons=['c40_minus_s40','c80_minus_s80','interaction_(c80-s80)-(c40-s40)']
    for j,comp in enumerate(comparisons):
        rr=sorted([r for r in contrasts if r['comparison']==comp],key=lambda r:-number(r,'included_bandwidth_hz'))
        axes[0].plot([number(r,'included_bandwidth_hz')/1e6 for r in rr],[number(r,'difference') for r in rr],label=['C40 − S40','C80 − S80','Interaction'][j],color=COLORS[j],marker=MARKERS[j],ls=LINES[j])
    axes[0].set(xlabel='Included bandwidth (MHz)',ylabel='Log-power contrast (dB)',title='(a) Full 20 MHz is primary');axes[0].legend(fontsize=8)
    axes[0].axvline(10,color='#777777',ls=':',lw=.8)
    for j,group in enumerate(('stability','cable')):
        rr=[r for r in metrics if r['experiment']==group];vals=np.array([number(r,'storage_mid_code_fraction')*100 for r in rr])
        axes[1].scatter(np.full(len(vals),j)+np.linspace(-.12,.12,len(vals)),vals,s=15,facecolors='none',edgecolors=COLORS[j],marker=MARKERS[j])
    axes[1].set_xticks([0,1],['Stability','Cable']);axes[1].set(ylabel='Stored samples equal to 128 (%)',title='(b) PCM8 code-occupancy diagnostic')
    save(fig,'K4-S2_bandwidth_and_quality',['edge_sensitivity_contrasts.csv','record_metrics.csv'],
         '10 MHz point is a labeled legacy-truncation diagnostic, not the primary band. Storage-code occupancy cannot be interpreted as ADC ENOB.')

    if len(daily.get('dates',[]))>=2:
        fig,ax=make(2.6)
        ds=rows('verified_day1_template_scores.csv');xx=np.arange(len(ds))
        ax.plot(xx,[number(r,'daily_mean_template_local_corr') for r in ds],marker='o',label='Daily local-contrast r')
        confirmed=daily.get('reference_is_confirmed_experiment_day1',False)
        ax.plot(xx,[number(r,'reference_peak_presence_score') for r in ds],marker='s',ls='--',label='Day 1 candidate presence' if confirmed else 'First-available-date candidate presence')
        ax.set_xticks(xx,[r['acquisition_date'] for r in ds],rotation=35);ax.set(xlabel='Confirmed acquisition date',ylabel='Descriptive template score');ax.legend()
        save(fig,'K4-S3_dated_reference_scores',['verified_day1_template_scores.csv'],'Only confirmed dates and a reviewed cohort; first available date is not assumed to be experiment Day1; no classification accuracy.')
    for p in provenance:
        for ext in ('pdf','png'):
            path=OUT/(p['figure']+'.'+ext);p[ext+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (ROOT/'figure_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Saved {len(provenance)} paired PDF/600-dpi PNG figures, width={WIDTH:.6f} in')


if __name__=='__main__': main()
