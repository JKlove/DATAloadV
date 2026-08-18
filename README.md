# DataloadV 电生理数据平台

读取、浏览、预处理与简单特征提取的桌面工作台（介入式 BCI 研究数据工具）。

## 功能概览（v1 目标）

- **数据管理**：EDF/EDF+、BDF、GDF、BrainVision、FIF、EEGLAB、CNT、EGI、BCI-IV .mat、NWB、Intan、Open Ephys、Blackrock、CSV/TXT、HDF5——单文件或整目录批量导入，元数据表浏览筛选
- **波形浏览**：多通道滚动/缩放、事件标记叠加与跳转、通道启用/排序/增益/坏道标记
- **预处理**：带通/陷波滤波、重参考、降采样、坏导联处理、事件分段——步骤链可编排、可复现
- **特征提取**：PSD（Welch）、标准+自定义频带功率、时域统计量
- **批处理**：管线批量套用，逐文件进度/日志/错误报告，可取消
- **导出**：特征 CSV/HDF5、分段 HDF5/FIF，附 JSON 管线溯源 sidecar

## 快速开始

```bash
conda activate dlv
dataloadv
```

环境搭建完整命令见 [HANDOFF.md](HANDOFF.md)；开发计划见 [plan.md](plan.md)，当前进度见 [STATUS.md](STATUS.md)。

## 技术栈

Python 3.10 · PySide6 · pyqtgraph · MNE · numpy/scipy/pandas · pydantic v2

（截图将在 M5 收尾时补充）
