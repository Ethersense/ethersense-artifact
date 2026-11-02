"""Plot only measured derived spectra/tables; existing notebook colors reused."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path("results/ethersense_supplemental")
FIG=ROOT/"figures"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"font.family":"Microsoft YaHei","font.size":11,"axes.unicode_minus":False,"axes.spines.top":False,"axes.spines.right":False,"pdf.fonttype":42,"savefig.dpi":220,"axes.grid":True,"grid.alpha":.18})
BLUE="#154360"
RED="#B71C1C"
GRAY="#78909C"
COLORS=[BLUE,RED,"#247A47","#A45B08"]
summary=json.loads((ROOT/"analysis_summary.json").read_text(encoding="utf-8"))
z=dict(np.load(ROOT/"derived_spectra.npz"))
freq=z["offset_hz"]
band=(np.abs(freq)<=5e6)&(np.abs(freq)>5000)
metrics={x["record_id"]:x for x in summary["metrics"]}
features=list(csv.DictReader((ROOT/"feature_tracking.csv").open(encoding="utf-8-sig")))
definitions=list(csv.DictReader((ROOT/"feature_definitions.csv").open(encoding="utf-8-sig")))
manifest=[]


def save(fig,name,caption,data):
    fig.savefig(FIG/(name+".png"))
    fig.savefig(FIG/(name+".pdf"))
    plt.close(fig)
    manifest.append({"figure":name,"caption":caption,"underlying_data":data,"x_axis_orientation":"channel_1+j*channel_2 offset; I/Q order unconfirmed unless explicitly two candidate RF axes"})


def series(rid,normalize=False):
    y=10*np.log10(z[rid+"_psd"])
    if normalize:
        y=y-np.median(y[band])
    return np.where(band,y,np.nan)


def foot(fig,text):
    fig.text(.5,.015,text,ha="center",fontsize=9,color="#444444")


def finish(fig,title):
    fig.suptitle(title,fontsize=15)
    fig.tight_layout(rect=(0,.045,1,.96))


fig,axes=plt.subplots(2,2,figsize=(13,8),sharex=True,sharey=True)
for ax,pair in zip(axes.ravel(),summary["A_pairs"]):
    distance=pair["absolute_distance_m"]
    for rid,color,label,style in ((pair["positive_record_id"],BLUE,f"+{distance} m", "-"),(pair["negative_record_id"],RED,f"−{distance} m","-"),("A09",GRAY,"base","--")):
        ax.plot(freq/1e6,series(rid),color=color,lw=.8,ls=style,label=label)
    ax.set_title(f"|距离|={distance} m；两次采集相隔 {pair['measurement_time_gap_s']} s")
    ax.legend(loc="upper right",fontsize=9)
    ax.set(xlabel="编码频偏 Δf (MHz)",ylabel="相对数字 PSD (dB/Hz)",xlim=(-5,5))
finish(fig,"A：相同绝对距离的正负方向频谱")
foot(fig,"PCM16/32768；20 MHz 中心；I/Q 顺序与增益待确认；每个位置一次采集")
save(fig,"A01_direction_spectra","四组正负方向与共同背景对比，同频率网格与相同纵轴；中心 ±5 kHz 留缺口。","output/A*_spectra.npz; data_index.csv")

fig,axes=plt.subplots(1,2,figsize=(12,4.7))
for sign,color,label in ((1,BLUE,"正向：沿导线"),(-1,RED,"负向：另一侧")):
    rows=sorted((m for m in metrics.values() if m["experiment"]=="A" and m["distance_m"] is not None and np.sign(m["distance_m"])==sign),key=lambda m:abs(m["distance_m"]))
    x=[abs(m["distance_m"]) for m in rows]
    axes[0].plot(x,[m["passband_power_db_digital_unit2"] for m in rows],marker="o" if sign==1 else "s",color=color,label=label)
    axes[0].vlines(x,[m["within_file_band_power_q10_db"] for m in rows],[m["within_file_band_power_q90_db"] for m in rows],color=color,lw=3,alpha=.55)
    axes[1].plot(x,[m["feature_band_to_local_floor_ratio_db"] for m in rows],marker="o" if sign==1 else "s",color=color,label=label)
axes[0].axhline(metrics["A09"]["passband_power_db_digital_unit2"],color=GRAY,ls="--",label="base")
for ax in axes:
    ax.set(xlabel="绝对距离 (m)",xticks=range(1,5))
    ax.legend(fontsize=9)
axes[0].set_ylabel("10 MHz 频带数字功率 (dB)")
axes[1].set_ylabel("AF01 峰区 / 局部谱底 (dB)")
finish(fig,"A：方向差异的两种数字指标")
foot(fig,"竖线为文件内16子区间的10–90分位范围，非置信区间；连线仅辅助读图")
save(fig,"A02_direction_strength","左图为数字功率与文件内分位范围，右图为固定候选峰区相对局部谱底；增益和时间混杂未排除。","quantitative_metrics.csv; A_direction_pairs.csv; feature_definitions.csv")

fig,axes=plt.subplots(1,2,figsize=(12,4.7))
a_ref=next(float(v["reference_offset_hz"]) for v in definitions if v["experiment"]=="A")
zoom=np.abs(freq-a_ref)<40_000
for rid,color,style,label in (("A04",BLUE,"-","+1 m"),("A05",RED,"-","−1 m"),("A01","#247A47","-","+4 m"),("A08","#A45B08","-","−4 m"),("A09",GRAY,"--","base")):
    axes[0].plot(freq[zoom]/1e6,series(rid)[zoom],color=color,ls=style,label=label)
    axes[1].plot(freq[zoom]/1e6,z[rid+"_contrast"][zoom],color=color,ls=style,label=label)
axes[0].set_ylabel("相对数字 PSD (dB/Hz)")
axes[1].set_ylabel("相对局部谱底 (dB)")
for ax in axes:
    ax.set_xlabel("编码频偏 Δf (MHz)")
    ax.legend(fontsize=9)
finish(fig,"A：AF01 候选峰局部对比")
foot(fig,"该峰是候选条件关联特征；背景、环境载波或接收器伪迹等来源尚未排除")
save(fig,"A03_peak_comparison","A04参考文件筛出的一个条件增强候选峰，比较数字幅度与局部谱底对比；完整主峰见CSV。","feature_definitions.csv; feature_tracking.csv; derived_spectra.npz")

# Rebinning is linear-power averaging, not downsampled peak selection.
mask=(freq>=-5e6)&(freq<5e6)
selected=np.flatnonzero(mask)
trim=len(selected)//8*8
indices=selected[:trim].reshape(-1,8)
bins=freq[indices].mean(axis=1)/1e6
image=np.array([10*np.log10(z[f"B{i:02d}_psd"][indices].mean(axis=1)) for i in range(1,11)])
image[:,np.abs(bins)<.005]=np.nan
fig,ax=plt.subplots(figsize=(12,5.5))
im=ax.imshow(image,aspect="auto",origin="lower",extent=(bins[0],bins[-1],.5,10.5),cmap="viridis",interpolation="nearest")
fig.colorbar(im,ax=ax,label="相对数字 PSD (dB/Hz)")
ax.set(xlabel="编码频偏 Δf (MHz)",ylabel="沿线距离 (m)",yticks=range(1,11))
finish(fig,"B：1–10 m 频谱矩阵")
foot(fig,"每像素平均8个FFT频点（约2.44 kHz）；颜色范围覆盖全部有效数据；并非校准场强")
save(fig,"B01_distance_spectra","各距离的频谱矩阵，用线性功率平均8频点减小展示体积，未用插值增强分辨率。","output/B*_spectra.npz; data_index.csv")

fig,axes=plt.subplots(1,2,figsize=(12,4.7))
rows=[metrics[f"B{i:02d}"] for i in range(1,11)]
x=np.arange(1,11)
axes[0].plot(x,[m["passband_power_db_digital_unit2"] for m in rows],"o-",color=BLUE)
axes[0].vlines(x,[m["within_file_band_power_q10_db"] for m in rows],[m["within_file_band_power_q90_db"] for m in rows],color=BLUE,lw=3,alpha=.5)
axes[0].axhline(metrics["A09"]["passband_power_db_digital_unit2"],color=GRAY,ls="--",label="共同 base（较早采集）")
axes[0].legend(fontsize=9)
axes[0].set_ylabel("10 MHz 频带数字功率 (dB)")
axes[1].plot(x,[m["feature_band_to_local_floor_ratio_db"] for m in rows],"s-",color=RED)
axes[1].axhline(0,color=GRAY,ls="--")
axes[1].set_ylabel("4个固定峰区 / 局部谱底 (dB)")
for ax in axes:
    ax.set(xlabel="沿线距离 (m)",xticks=x)
finish(fig,"B：距离与数字信号强度")
foot(fig,"均为实测点；未拟合传播衰减模型；竖线为文件内10–90分位范围；距离与采集时间共变")
save(fig,"B02_distance_strength","左为整段平均数字功率，右为1m选定的四个候选峰固定频窗与局部谱底之比；二者趋势不能互换。","quantitative_metrics.csv; B_threshold_sensitivity.csv")

fig,axes=plt.subplots(2,2,figsize=(12,7.7),sharex=True)
for ax,definition,color in zip(axes.ravel(),[d for d in definitions if d["experiment"]=="B"],COLORS):
    fid=definition["feature_id"]
    r=[next(v for v in features if v["record_id"]==f"B{i:02d}" and v["feature_id"]==fid) for i in range(1,11)]
    ax.plot(x,[float(v["local_floor_contrast_db"]) for v in r],"o-",color=color)
    bg=float(r[0]["background_contrast_db_near_frequency"])
    ax.axhline(bg,color=GRAY,ls="--",label="base峰对比")
    ax.axhline(max(6,bg+6),color=RED,ls=":",label="6 dB 分析规则")
    ax.set_title(f"{fid}；Δf={float(definition['reference_offset_hz'])/1e6:.6f} MHz")
    ax.set(xlabel="距离 (m)",ylabel="峰 / 局部谱底 (dB)",xticks=x)
    ax.legend(fontsize=8)
finish(fig,"B：固定参考峰随距离的保留情况")
foot(fig,"阈值是分析筛选规则，未验证为电器识别阈值；候选峰不能直接视为设备专属指纹")
save(fig,"B03_feature_tracking","固定使用1m参考峰，在各距离±5kHz内寻峰；共同背景峰对比用相同寻峰窗；不报告识别准确率。","feature_tracking.csv; feature_definitions.csv; B_threshold_sensitivity.csv")

labels={"C01":"电瓶车断开","C02":"全部连接","C03":"电器2断开","C04":"全部断开"}
fig,axes=plt.subplots(1,2,figsize=(13,4.9),sharex=True)
for rid,color,style in zip(labels,COLORS,("-","-","-","--")):
    axes[0].plot(freq/1e6,series(rid),lw=.7,color=color,ls=style,label=labels[rid])
    axes[1].plot(freq/1e6,series(rid,True),lw=.7,color=color,ls=style,label=labels[rid])
for ax in axes:
    ax.set(xlabel="编码频偏 Δf (MHz)",xlim=(-5,5))
    ax.legend(fontsize=9,loc="upper right")
axes[0].set_ylabel("相对数字 PSD (dB/Hz)")
axes[1].set_ylabel("相对本文件频谱中位数 (dB)")
finish(fig,"C：四种原始标签条件的频谱")
foot(fig,"19.6 MHz中心；电器2身份及另一台运行状态待确认；右图只移除整体标量幅度差")
save(fig,"C01_condition_spectra","四种字面标签比较；左图原数字谱，右图减去各自频带谱中位数以观察形态，未用归一化结果判断功率叠加。","derived_spectra.npz; quantitative_metrics.csv")

fig,ax=plt.subplots(figsize=(12,4.3))
cp=summary["C"]["peak_association"]
heat=np.array([[v[f"{rid}_local_contrast_db"] for v in cp] for rid in labels])
im=ax.imshow(heat,cmap="viridis",aspect="auto",interpolation="nearest")
for i in range(4):
    for j in range(len(cp)):
        ax.text(j,i,f"{heat[i,j]:.1f}",ha="center",va="center",color="white" if heat[i,j]<np.median(heat) else "black",fontsize=9)
ax.set_yticks(range(4),[labels[rid] for rid in labels])
ax.set_xticks(range(len(cp)),[f"{v['feature_id']}\nΔf {v['offset_hz']/1e6:.3f}" for v in cp],fontsize=9)
ax.set_xlabel("代表性窄峰（编码频偏，MHz）")
fig.colorbar(im,ax=ax,label="峰 / 局部谱底 (dB)")
finish(fig,"C：主要共同窄峰对比（设备归属未确认）")
foot(fig,"严格的6 dB条件增强候选峰数为0；本图展示共同/背景代表峰，不能按列分配设备")
save(fig,"C02_peak_comparison","两种单设备字面标签与全部断开中的八个代表性窄峰，全部保留背景强峰；条件增强规则未筛出设备专属峰。","C_condition_peak_association.csv; feature_tracking.csv")

fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True)
pred=z["C_additive_prediction"]
for values,color,label,style in ((z["C02_psd"],RED,"全部连接实测","-"),(pred,BLUE,"P(车断)+P(电器2断)−P(全断)：条件预测","--")):
    y=np.where(band&(values>0),10*np.log10(np.maximum(values,1e-300)),np.nan)
    axes[0].plot(freq/1e6,y,color=color,lw=.7,ls=style,label=label)
ratio=np.where(band&(pred>0),10*np.log10(z["C02_psd"]/np.maximum(pred,1e-300)),np.nan)
axes[1].plot(freq/1e6,ratio,color=BLUE,lw=.7)
axes[1].axhline(0,color=GRAY,ls="--")
axes[0].set_ylabel("相对数字 PSD (dB/Hz)")
axes[0].legend(fontsize=9)
axes[1].set(xlabel="编码频偏 Δf (MHz)",ylabel="实测 / 条件预测 (dB)",xlim=(-5,5))
finish(fig,"C：简单功率相加的条件诊断")
foot(fig,f"全频带实测比预测高 {summary['C']['observed_vs_predicted_band_db']:.2f} dB；增益、独立源和背景恒定等前提未核实")
save(fig,"C03_conditional_additivity","先在线性功率域减一次共同背景，再计算逐频点及积分残差；差异不是耦合或非线性机制的因果证据。","derived_spectra.npz; analysis_summary.json")

fig,axes=plt.subplots(3,1,figsize=(12,9),sharex=True)
for ax,group in zip(axes,"ABC"):
    ids=sorted(rid for rid in metrics if rid.startswith(group))
    palette=plt.get_cmap("tab10")
    for i,rid in enumerate(ids):
        mean=metrics[rid]["passband_power_db_digital_unit2"]
        y=z[rid+"_time_power_db"]-mean
        ax.plot((np.arange(len(y))+.5)/len(y),y,lw=2 if rid=="B01" else 1,color=palette(i%10),marker="o" if rid=="B01" else None,markersize=3,label=f"{rid}")
    ax.set_ylabel(f"{group}：相对本文件均值 (dB)")
    ax.legend(ncol=5,fontsize=8)
    ax.axhline(0,color=GRAY,ls="--")
axes[-1].set_xlabel("文件内相对采集时间（16个子区间）")
finish(fig,"质量检查：稳定设备状态下的接收幅度变化")
foot(fig,"子区间是同一次采集的相关片段，不能视为独立实验重复；B01变化约6 dB需复核")
save(fig,"Q01_within_file_variation","所有23个文件均展示16个时间子区间的频带功率变化，避免整段平均掩盖时间变化。","output/*_spectra.npz; quantitative_metrics.csv; derived_spectra.npz")

fig,axes=plt.subplots(2,1,figsize=(12,7.2),sharex=True)
for ax,sign in zip(axes,(1,-1)):
    for rid,color,label in (("B01",BLUE,"1–10 m组 1 m"),("C03",RED,"并联：电器2断开"),("C04",GRAY,"并联：全部断开")):
        center=20e6 if rid=="B01" else 19.6e6
        axis=center+sign*freq
        select=(axis>=15e6)&(axis<=24.6e6)&(np.abs(freq)>5000)
        order=np.argsort(axis)
        y=np.where(select,z[rid+"_contrast"],np.nan)
        ax.plot(axis[order]/1e6,y[order],color=color,lw=.7,label=label)
    ax.set_title("候选 RF 轴：f_RF = f_c "+("+" if sign==1 else "−")+" Δf（I/Q顺序未确认）")
    ax.set_ylabel("峰 / 局部谱底 (dB)")
    ax.legend(fontsize=9)
axes[-1].set_xlabel("候选实际频率 (MHz)；共同频带15–24.6 MHz")
finish(fig,"不同中心频率：分别对齐两种候选实际频率轴")
foot(fig,"未把不同中心频率的FFT数组直接相减；两种候选轴都保留，等待采集软件或I/Q记录确认")
save(fig,"Q02_frequency_axis_alignment","20MHz和19.6MHz中心的记录分别按fc±offset映射，共同频带裁剪后展示；两种方向的相关性不能确认I/Q约定。","derived_spectra.npz; frequency_axis_sensitivity.csv; data_index.csv")

fig,ax=plt.subplots(figsize=(12,5))
full_mask=np.abs(freq)>5000
for rid,color in zip(labels,COLORS):
    y=np.where(full_mask,10*np.log10(z[rid+"_psd"]),np.nan)
    ax.plot(freq/1e6,y,color=color,lw=.7,label=labels[rid])
for boundary in (-5,5):
    ax.axvline(boundary,color=GRAY,ls="--",lw=1.3)
ax.set(xlabel="完整采样频偏 Δf (MHz)",ylabel="相对数字 PSD (dB/Hz)",xlim=(-10,10))
ax.legend(fontsize=9)
finish(fig,"带宽检查：并联组完整20 MSPS采样频谱")
foot(fig,"主分析使用虚线之间的中心10 MHz；外侧能量保留作质量检查，不据此确认模拟接收带宽")
save(fig,"Q03_sampled_bandwidth","完整复样本频率范围约±10MHz，与用户声明的中心±5MHz分析带宽区分；全部连接在中间10MHz外的能量较大。","output/C*_spectra.npz; quantitative_metrics.csv")

(ROOT/"figure_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
lines=["# 图表与数据对应","","全部图表由实测数据生成。PNG用于预览，PDF为矢量版本。功率为数字单位，频率轴约定待确认。",""]
for item in manifest:
    lines += [f"## {item['figure']}","",f"![{item['caption']}](figures/{item['figure']}.png)","",item["caption"],"",f"数据：`{item['underlying_data']}`；脚本：`code/plot_supplemental.py`。",""]
(ROOT/"FIGURES.md").write_text("\n".join(lines),encoding="utf-8")
print("Generated",len(manifest),"figures in PNG and vector PDF")
