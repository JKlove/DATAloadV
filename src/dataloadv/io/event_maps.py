"""GDF 事件码 → 中文标签映射（BCI Competition IV 数据集 2a / 2b 官方码表）.

码表来源（2026-08-18 从官方描述 PDF 提取原文，非二手转述）：
- 2a: https://www.bbci.de/competition/iv/desc_2a.pdf
- 2b: https://www.bbci.de/competition/iv/desc_2b.pdf

两表合并后的完整对照（左边代码列是 mne 读取 GDF 时 annotation
description 里的数字字符串，如 "769"）：

    276   Idling EEG (eyes open)        静息（睁眼）
    277   Idling EEG (eyes closed)      静息（闭眼）
    768   Start of a trial              试次开始
    769   Cue onset left (class 1)      提示：左手（类1）
    770   Cue onset right (class 2)     提示：右手（类2）
    771   Cue onset foot (class 3)      提示：双脚（类3）     [仅 2a]
    772   Cue onset tongue (class 4)    提示：舌头（类4）     [仅 2a]
    781   BCI feedback (continuous)     BCI 反馈（连续）      [仅 2b]
    783   Cue unknown                   提示：未知（评估集）
    1023  Rejected trial                被拒绝试次
    1072  Eye movements                 眼动                 [2a；2b 数据中亦出现]
    1077  Horizontal eye movement       水平眼动             [仅 2b 校准期]
    1078  Vertical eye movement         垂直眼动             [仅 2b 校准期]
    1079  Eye rotation                  眼球旋转             [仅 2b 校准期]
    1081  Eye blinks                    眨眼                 [仅 2b 校准期]
    32766 Start of a new run            新 run 开始

注意：1077-1081 是 2b 校准会话里受试者按提示制造的伪迹标记（供伪迹
分析用），不是脑电类别；781 在 2b 每试次出现一次（反馈阶段）。
"""

from __future__ import annotations

from ..core.recording import EventTable

# 官方码表（合并 2a/2b；键为事件码整数）
GDF_CODE_LABELS: dict[int, str] = {
    276: "静息（睁眼）",
    277: "静息（闭眼）",
    768: "试次开始",
    769: "提示：左手（类1）",
    770: "提示：右手（类2）",
    771: "提示：双脚（类3）",
    772: "提示：舌头（类4）",
    781: "BCI 反馈（连续）",
    783: "提示：未知（评估集）",
    1023: "被拒绝试次",
    1072: "眼动",
    1077: "水平眼动",
    1078: "垂直眼动",
    1079: "眼球旋转",
    1081: "眨眼",
    32766: "新 run 开始",
}


def gdf_label(code: str) -> str:
    """单个 GDF 事件码（mne description 字符串）→ 中文标签.

    非数字或码表外的代码原样返回（不猜——宁缺毋滥，未知码在界面照显数字）。
    """
    try:
        n = int(float(code))
    except (TypeError, ValueError):
        return str(code)
    return GDF_CODE_LABELS.get(n, str(code))


def apply_gdf_labels(events: EventTable) -> EventTable:
    """把 GDF 数字事件码批量翻译为中文标签（code 保留原数字串，label 换中文）.

    GDF 事件在 mne 里是 annotations，description 为 "769" 这类数字字符串
    （2a/2b 实测确认）；翻译后 EventTable.code 仍是数字串（分段、导出、
    与文献对照都用它），label 才是给人看的中文。
    """
    events.label = [gdf_label(c) for c in events.code]
    return events
