# DataloadV 电生理数据平台

读取、浏览、预处理与简单特征提取的桌面工作台（介入式 BCI 研究数据工具）。

## 功能概览（v1）

- **数据管理**：EDF/EDF+、BDF、GDF、BrainVision、FIF、EEGLAB、CNT、EGI、BCI-IV .mat、NWB、Intan（rhd/rhs）、Open Ephys、Blackrock、CSV/TXT、HDF5——单文件或整目录批量导入，元数据表浏览筛选；打开时按文件头魔数校验格式（扩展名不符以内容为准）
- **波形浏览**：多通道滚动浏览（一屏时长选择+翻屏/±1s 步进/滚轮平移/键盘导航）、底部总览时间轴滑块（拖动/点击定位）、行居中开关与通道直流偏移显示、增益（滑杆+精确输入框）、幅值标尺、事件标记叠加与跳转、通道启用/坏道标记
- **预处理**：带通/陷波滤波、重参考、降采样、坏导联处理、时间窗裁剪、事件分段——步骤链可编排、可序列化复现
- **特征提取**：PSD（Welch）、标准+自定义频带功率、时域统计量；raw 全量摘要或 epochs 逐段；「用当前显示窗口」一键预填时间窗
- **批处理**：右侧面板组好的管线+特征链批量套用到工作区任意文件子集；逐文件进度/日志/错误报告（失败行双击看日志），随时取消，UI 全程响应
- **导出**：特征 CSV（UTF-8 BOM，Excel 直接开）/HDF5、分段 HDF5/FIF，附 JSON 管线溯源 sidecar（步骤参数+文件清单+库版本）
- **设置**：批处理默认线程数、数据缓存预算（GB）、默认导出目录

## 快速开始

```bash
conda activate dlv
dataloadv          # 或 python -m dataloadv
```

典型流程：

1. 文件 → 导入文件/文件夹（工作区树与元数据表填充）
2. 双击任意录制浏览波形；右键通道可标记坏道
3. 右侧管线面板「添加步骤/添加特征」组链 → 「预览当前文件」核对效果（PSD 对比）
4. 处理 → 批处理…：勾选文件、选导出目录 → 开始（逐文件进度，双击失败行看日志）
5. 特征结果 tab → 导出 CSV / HDF5（sidecar 自动随行）

## 验证

- 单测：`QT_QPA_PLATFORM=offscreen pytest`（193 项，含真实羊 BDF（.edf 误标）与真实 GDF 数据）
- 端到端：`python scripts/e2e_m1.py` … `e2e_m5.py`（各里程碑真实数据验收，幂等可反复跑）

环境搭建完整命令见 [HANDOFF.md](HANDOFF.md)；开发计划见 [plan.md](plan.md)，当前进度见 [STATUS.md](STATUS.md)；**说明·运行·使用·调试一册通览见 [MANUAL.md](MANUAL.md)**。

## 技术栈

Python 3.10 · PySide6 · pyqtgraph · MNE · numpy/scipy/pandas · pydantic v2 · neo（可选）· pynwb（可选）
