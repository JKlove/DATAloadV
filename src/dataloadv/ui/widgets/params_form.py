"""参数自动表单：从 pydantic 参数模型生成 Qt 编辑器（新增步骤零 UI 代码）.

类型 → 控件映射：
- ``float`` / ``Optional[float]`` → QDoubleSpinBox（可勾选开关；不勾=None）
- ``int`` → QSpinBox
- ``bool`` → QCheckBox
- ``Literal["a","b"]`` → QComboBox（选项取自 Field.description 或枚举值）
- ``list[float]`` / ``list[str]`` → QLineEdit（逗号/空格分隔解析）
- ``Optional[tuple[float,float]]`` → QLineEdit（"a, b"；"无"→None；端点可用"无"）

数值范围/小数位优先取 Field 的 ``json_schema_extra``（min/max/decimals/unit），
没给就用宽泛默认——表单永不因范围问题卡死用户。
"""

from __future__ import annotations

import logging
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..strings_zh import S

logger = logging.getLogger(__name__)


class _OptionalFloatBox(QWidget):
    """带"启用"开关的浮点输入：开关关 = None（如带通某一侧不滤）."""

    def __init__(self, default: float | None, extra: dict, parent=None) -> None:
        super().__init__(parent)
        self.check = QCheckBox()
        self.spin = QDoubleSpinBox()
        self.spin.setRange(float(extra.get("min", 0.0)), float(extra.get("max", 10000.0)))
        self.spin.setDecimals(int(extra.get("decimals", 2)))
        self.spin.setValue(default if default is not None else 0.0)
        if "unit" in extra:
            self.spin.setSuffix(f" {extra['unit']}")
        self.check.toggled.connect(self.spin.setEnabled)
        on = default is not None
        self.check.setChecked(on)
        self.spin.setEnabled(on)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.spin)

    def value(self) -> float | None:
        return round(self.spin.value(), self.spin.decimals()) if self.check.isChecked() else None


class _ChannelPickerEdit(QWidget):
    """通道选择控件（M15）：按钮弹出勾选对话框，替代 channels 字段的手输文本框.

    语义对齐 params 约定：**空选择 = 全部数据通道**（按钮显示「全部（N 通道）」、
    value() 返回 []）——避免"全不勾"造成无通道可算的困惑；选了子集则按钮显示
    「已选 k/N」并按候选顺序输出勾选名。仅当表单注入了通道候选时启用
    （ParamsForm 的 channel_candidates 参数；无候选回退 QLineEdit 旧行为）。
    """

    edited = Signal()

    def __init__(self, candidates: list[str], current: list[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._candidates = list(candidates)
        self._selected = [c for c in self._candidates if c in set(current)]
        self._btn = QPushButton()
        self._btn.clicked.connect(self._open_dialog)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._btn)
        self._refresh_text()

    def _refresh_text(self) -> None:
        n, k = len(self._candidates), len(self._selected)
        self._btn.setText(
            S.CH_PICK_ALL_FMT.format(n=n) if k in (0, n)
            else S.CH_PICK_SEL_FMT.format(k=k, n=n))

    def _open_dialog(self) -> None:
        """弹出勾选对话框（全选/清空快捷键 + 确定/取消）."""
        dlg = QDialog(self)
        dlg.setWindowTitle(S.CH_PICK_TITLE)
        lay = QVBoxLayout(dlg)
        hint = QLabel(S.CH_PICK_EMPTY_HINT)
        lay.addWidget(hint)
        lst = QListWidget()
        for name in self._candidates:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if name in set(self._selected)
                else Qt.CheckState.Unchecked)
            lst.addItem(item)
        lay.addWidget(lst, 1)
        quick = QHBoxLayout()
        btn_all = QPushButton(S.CH_PICK_BTN_ALL)
        btn_none = QPushButton(S.CH_PICK_BTN_NONE)

        def _set_all(on: bool):
            for i in range(lst.count()):
                lst.item(i).setCheckState(
                    Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

        btn_all.clicked.connect(lambda: _set_all(True))
        btn_none.clicked.connect(lambda: _set_all(False))
        quick.addWidget(btn_all)
        quick.addWidget(btn_none)
        quick.addStretch(1)
        lay.addLayout(quick)
        btns = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        lay.addLayout(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        picked = {lst.item(i).text()
                  for i in range(lst.count())
                  if lst.item(i).checkState() == Qt.CheckState.Checked}
        new_sel = [c for c in self._candidates if c in picked]  # 候选序稳定
        if new_sel != self._selected:
            self._selected = new_sel
            self._refresh_text()
            self.edited.emit()

    def value(self) -> list[str]:
        """当前选择（空列表 = 全部数据通道；非空按候选顺序）."""
        return list(self._selected)


class ParamsForm(QWidget):
    """一个处理步骤的参数编辑表单.

    :param step: ProcStep 实例（提供 params_cls）
    :param params: 当前参数值（新步骤=默认值；选中已有步骤=其当前值）
    :param channel_candidates: 通道名候选（M15；特征表单注入当前录制的通道
        名——channels 字段渲染为勾选控件；None/步骤表单=旧行为）
    :signal edited: 任一控件被编辑（面板据此把值写回步骤条目）
    :raises ValueError: collect() 时若解析失败（中文信息，含字段名）
    """

    edited = Signal()

    def __init__(self, step, params: BaseModel, parent=None,
                 channel_candidates: list[str] | None = None) -> None:
        super().__init__(parent)
        self._step = step
        self._params = params
        self._ch_candidates = channel_candidates
        self._getters: dict[str, object] = {}  # 字段名 -> 取值 callable
        form = QFormLayout(self)
        form.setContentsMargins(4, 4, 4, 4)
        for name, field in type(params).model_fields.items():
            widget = self._make_editor(name, field, getattr(params, name))
            if widget is None:
                continue
            label = field.title or name
            form.addRow(label, widget)
        if self._getters:
            self.setToolTip("修改参数后自动保存到步骤")

    # ------------------------------------------------------------------ 控件工厂

    def _make_editor(self, name: str, field: FieldInfo, value) -> QWidget | None:
        """按字段类型建编辑器，登记取值器；未知类型跳过（保持默认值）."""
        extra: dict = field.json_schema_extra or {}
        anno = field.annotation
        origin = get_origin(anno)

        # Literal 枚举 → 下拉框
        if origin is Literal:
            options = get_args(anno)
            combo = QComboBox()
            combo.addItems([str(o) for o in options])
            combo.setCurrentText(str(value))
            combo.currentIndexChanged.connect(lambda *_: self.edited.emit())
            self._getters[name] = (lambda c=combo, opts=options:
                                   opts[c.currentIndex()])
            return combo

        # bool → 复选框
        if anno is bool:
            box = QCheckBox()
            box.setChecked(bool(value))
            box.toggled.connect(lambda *_: self.edited.emit())
            self._getters[name] = box.isChecked
            return box

        # Optional[float] → 带开关的浮点框
        if origin is Union and type(None) in get_args(anno) and float in get_args(anno):
            box = _OptionalFloatBox(value, extra)
            box.check.toggled.connect(lambda *_: self.edited.emit())
            box.spin.valueChanged.connect(lambda *_: self.edited.emit())
            self._getters[name] = box.value
            return box

        # int → 整数框
        if anno is int:
            spin = QSpinBox()
            spin.setRange(int(extra.get("min", 0)), int(extra.get("max", 10**6)))
            spin.setValue(int(value))
            if "unit" in extra:
                spin.setSuffix(f" {extra['unit']}")
            spin.valueChanged.connect(lambda *_: self.edited.emit())
            self._getters[name] = spin.value
            return spin

        # float → 浮点框
        if anno is float:
            spin = QDoubleSpinBox()
            spin.setRange(float(extra.get("min", -1e6)), float(extra.get("max", 1e6)))
            spin.setDecimals(int(extra.get("decimals", 2)))
            spin.setValue(float(value))
            if "unit" in extra:
                spin.setSuffix(f" {extra['unit']}")
            spin.valueChanged.connect(lambda *_: self.edited.emit())
            self._getters[name] = lambda: round(spin.value(), spin.decimals())
            return spin

        # channels 字段 + 有候选 → 勾选控件（M15；空=全部数据通道的语义
        # 由控件三态文案承载，value 返回 list[str] 与旧文本框完全兼容）
        if name == "channels" and self._ch_candidates:
            picker = _ChannelPickerEdit(self._ch_candidates, value or [])
            picker.edited.connect(lambda: self.edited.emit())
            self._getters[name] = picker.value
            return picker

        # list[float] / list[str] → 文本框（逗号分隔）
        if origin is list:
            edit = QLineEdit(_format_list(value))
            if field.description:
                edit.setPlaceholderText(field.description)
            edit.editingFinished.connect(lambda: self.edited.emit())
            item_type = get_args(anno)[0] if get_args(anno) else str
            self._getters[name] = (lambda e=edit, t=item_type:
                                   _parse_list(e.text(), t))
            return edit

        # Optional[tuple[float, float]] → 文本框（"a, b"）
        if origin is tuple or anno is tuple:
            edit = QLineEdit("" if value is None else _format_list(list(value)))
            edit.setPlaceholderText("如 无,0 或 -0.5,0；整项填 无 表示不做")
            edit.editingFinished.connect(lambda: self.edited.emit())
            self._getters[name] = lambda e=edit: _parse_pair(e.text())
            return edit

        logger.warning("参数字段 %s.%s 类型 %s 无编辑器，保持默认值", self._step.step_id, name, anno)
        return None

    # ------------------------------------------------------------------ 取值

    def collect(self) -> BaseModel:
        """从控件收集参数并构造模型（解析失败抛 ValueError，中文）."""
        data = {}
        for name, getter in self._getters.items():
            try:
                data[name] = getter()
            except ValueError as e:
                raise ValueError(f"字段「{type(self._params).model_fields[name].title or name}」：{e}") from e
        try:
            return self._step.make_params(data)
        except Exception as e:  # noqa: BLE001 - pydantic 校验失败信息已是中文友好
            raise ValueError(str(e)) from e


# ---------------------------------------------------------------------- 解析

_NONE_WORDS = {"", "无", "none", "null", "-"}


def _format_list(value: list) -> str:
    """list → 展示文本（None 元素与空列表 → 空串）."""
    if value is None:
        return ""
    return "，".join("无" if v is None else str(v) for v in value)


def _parse_list(text: str, item_type) -> list:
    """逗号/中英文逗号/空格分隔文本 → list[float] 或 list[str]."""
    tokens = [t for t in text.replace("，", ",").replace(",", " ").split() if t]
    if item_type is float:
        try:
            return [float(t) for t in tokens]
        except ValueError as e:
            raise ValueError("需要数字（逗号分隔），如 50, 100") from e
    return [str(t) for t in tokens]


def _parse_pair(text: str) -> tuple[float | None, float | None] | None:
    """'起,止' → 元组；端点可为 无；整项 无/空 → None（不做基线）."""
    t = text.strip()
    if t.lower() in _NONE_WORDS:
        return None
    parts = [p.strip() for p in t.replace("，", ",").split(",")]
    if len(parts) != 2:
        raise ValueError("格式应为「起,止」（两个数，逗号分隔）")

    def _one(p: str) -> float | None:
        if p.lower() in _NONE_WORDS:
            return None
        try:
            return float(p)
        except ValueError as e:
            raise ValueError("端点必须是数字或「无」") from e

    return (_one(parts[0]), _one(parts[1]))
