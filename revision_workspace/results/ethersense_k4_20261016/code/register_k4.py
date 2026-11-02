"""Register pointers in the shared project without modifying the paper/old reports."""
from __future__ import annotations
import json
import os
from pathlib import Path
import runtime_limits

ROOT=Path(__file__).resolve().parent.parent
WORKSPACE=ROOT.parent.parent
PROJECT=Path(os.environ.get('ETHERSENSE_K4_PROJECT','.'))


def new_or_identical(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_text(encoding='utf-8')!=text: raise FileExistsError('Will not replace existing project registration: '+str(path))
    if not path.exists(): path.write_text(text,encoding='utf-8')


def main():
    inv=json.loads((ROOT/'data_inventory.json').read_text(encoding='utf-8'))
    pointer=PROJECT/'07_experiments/data/received_20261016_k4_source_workspace/data_pointer.json'
    data={'workspace':str(WORKSPACE),'source_archive':inv['sources'][0]['archive'],'results':str(ROOT),'data_index':str(ROOT/'data_index.csv'),
          'report':str(ROOT/'EtherSense_K4补充实验分析报告.pdf'),'full_spectra_cache':str(ROOT/'output'),
          'initial_source_records':58,'bands_hz':{'stability':[1577e6,1597e6],'cable':[10e6,30e6]},
          'label_correction':'s150cm-4.wav -> S160 repeat4 (virtual metadata only)',
          'unresolved':'actual dates, gain/AGC, IQ convention, antenna/power/configuration, distance object; no source OFF controls',
          'raw_files_modified':False,'live_paper_modified':False}
    new_or_identical(pointer,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    new_or_identical(pointer.parent/'README.md','# K4原始数据与结果入口\n\n原始附件不复制、不改名；data_pointer.json指向本会话真实原件、完整数据索引、全谱缓存与结果。所有日期/增益缺项必须先核实，不能从文件名10day推算10个实际日期。新结果不覆盖10/14旧补充实验或原论文。\n')
    wrapper='''"""Run current K4 tools using source pointers, without copying raw data."""
import argparse,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('action',choices=('audit','check-cache','refresh'));a=p.parse_args()
pointer=Path(__file__).resolve().parent.parent/'data/received_20261016_k4_source_workspace/data_pointer.json'
cfg=json.loads(pointer.read_text(encoding='utf-8'));workspace=Path(cfg['workspace']);script=Path(cfg['results'])/'code/update_k4.py'
if not script.is_file(): raise FileNotFoundError('Original workspace unavailable; no stale-copy fallback')
subprocess.run([sys.executable,str(script),a.action],cwd=str(workspace),check=True)
'''
    new_or_identical(PROJECT/'07_experiments/code/run_k4_20261016.py',wrapper)
    index=f'''# EtherSense K4补充实验结果索引（2026-10-16）

产出：{ROOT.as_posix()}。

- [中文报告PDF]({(ROOT/'EtherSense_K4补充实验分析报告.pdf').as_posix()})
- [数据索引与定量数据本]({(ROOT/'EtherSense_K4_数据索引与定量结果.xlsx').as_posix()})
- [六组主图PDF]({(ROOT/'EtherSense_K4_六组主图.pdf').as_posix()})
- [PNG/PDF图表索引]({(ROOT/'FIGURES.md').as_posix()})
- [英文实验结果]({(ROOT/'paper/K4_Experiment_Results_EN.md').as_posix()})
- [中文审稿回复]({(ROOT/'paper/K4_审稿回复_CN.md').as_posix()})
- [英文Summary of Changes草稿]({(ROOT/'paper/K4_Summary_of_Changes_EN.md').as_posix()})
- [源码和派生频谱资料包]({(ROOT/'EtherSense_K4_结果与复现代码.zip').as_posix()})

58份WAV完整CRC通过；RF64/PCM8/双通道20MSPS。稳定性1587MHz、弯直20MHz，均完整20MHz主分析，两个频段不混算。s150cm-4在索引更正为S160第4次，原件不改。

当前仅可支持记录级重复性和布置敏感性描述：稳定性全带数字功率范围0.341dB、候选最大偏移915.53Hz，但日期/增益未核实、稳定性保存码值仅127/128/129，不能据此宣布十天或免训练。40/80cm C−S全带数字功率差+0.532/+0.451dB，未知增益/顺序/几何不能做因果归因；同条件四份为技术重复。C5/C13/C15部分补充，C20未解决。

轻量更新入口：07_experiments/code/run_k4_20261016.py；HISTORY_UPDATE.md说明历史隔离和cohort审核。19.66GB原始内容在致远G4核611.41秒完成，输出已取回，预留已释放。未改原论文、审稿状态、旧报告或版本号。
'''
    new_or_identical(PROJECT/'reports/20261016_K4补充实验结果索引.md',index)
    manifest=PROJECT/'MANIFEST.md';existing=manifest.read_text(encoding='utf-8');heading='## 2026-10-16 K4补充实验资料'
    if heading not in existing:
        with manifest.open('a',encoding='utf-8') as f:
            f.write('\n'+heading+'\n\n58个RF64 PCM8新文件已完整校验，完整20MHz分组分析、六主图/两补充图、中英报告与历史隔离更新流程见reports/20261016_K4补充实验结果索引.md；源/结果指针在07_experiments/data/received_20261016_k4_source_workspace/，代码入口run_k4_20261016.py。实际日期和接收设置未核实，不据此关闭K4或宣称十天/长期免重训；未改论文和旧报告。\n')
    print('Registered original-source/result pointers and lightweight runner in shared EtherSense project.')


if __name__=='__main__': main()
