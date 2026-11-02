# K4复现入口

从results/ethersense_k4_20261016目录运行；原始附件路径相对工作区由source_manifest.json指定。依赖numpy、scipy、matplotlib、reportlab、Pillow、openpyxl、PyMuPDF；实际版本见software_versions.json。

顺序：python code/audit_k4.py（头部/分组）→远端全量CRC/FFT（code/remote_k4.py，必须重新调度核实节点）→python code/analyze_k4.py→python code/summarize_k4.py→python code/verify_k4.py。

已有缓存的元数据更新用python code/update_k4.py refresh；它先保存旧产出。原始历史数据隔离/审核规则见../HISTORY_UPDATE.md。不要直接用remote_k4.py中的历史端口运行新任务；先pick_node选节点。

verified_rf64.py、verified_welch.py分别从上一轮已验证解析/PSD实现复用；后者增加PCM8无符号解码、按真实blockalign读取、全256码值直方图。code_reuse_provenance.json记录来源。论文图生成脚本（含样式库与绘图入口）未随本仓库发布，本仓库的派生NPZ/CSV已足以复算论文中的全部测量数值。

关键参数：FFT65536、Hann、50%重叠、16时间子区间、全20MHz积分、201点局部中位数、候选6dB/prominence3dB、固定±5kHz匹配。±5kHz/边缘50kHz等是分析设置，不是新编造的采集条件。无功率校准，不标dBm。runtime_limits.py设置数值库最多4线程与低优先级；全量原始19.66GB仅在远端计算。
