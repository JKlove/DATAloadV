"""时频图设置对话框（M13）：方法（四选）+ 参数调节.

手写 QFormLayout（settings_dialog 范式）——params_form.py 硬绑 ProcStep
模型不复用（浏览器时频参数是视图局部状态，无步骤模型）。

方法与参数（features.tfr.TfrConfig 的 UI 面）：
- 公共：频率下限/上限（上限按该文件 Nyquist 钳制为 SpinBox 最大值——
  超不了，无需事后校验）/频率点数；
- 按方法：morlet/multitaper=周期数系数（multitaper 另有 time_bandwidth）、
  stockwell=width、stft=窗长+重叠比例——方法切换时显隐对应行。

确定（校验 fmin<fmax）→ accept，调用方读 ``config()``。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...features.tfr import TfrConfig
from ..strings_zh import S

# 方法下拉顺序与 TfrConfig.method 取值（英文 key）的对应表
_METHOD_ITEMS: list[tuple[str, str]] = [
    ("morlet", S.TFR_METHOD_MORLET),
    ("multitaper", S.TFR_METHOD_MULTITAPER),
    ("stockwell", S.TFR_METHOD_STOCKWELL),
    ("stft", S.TFR_METHOD_STFT),
]


class TfrSettingsDialog(QDialog):
    """浏览器时频图的方法/参数编辑器——确定返回更新后的 TfrConfig."""

    def __init__(self, cfg: TfrConfig, sfreq: float, parent=None) -> None:
        """:param cfg: 当前配置（对话框初始值）。
        :param sfreq: 该文件采样率——频率上限按 Nyquist×0.49 钳制（TFR_FMAX_NYQ_RATIO）。
        """
        super().__init__(parent)
        self.setWindowTitle(S.TFR_DLG_TITLE)
        self._sfreq = float(sfreq)
        self._fmax_cap = TfrConfig().effective_fmax(sfreq)  # 钳制上限

        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)

        self._method = QComboBox()
        for key, text in _METHOD_ITEMS:
            self._method.addItem(text, key)
        cur = next((i for i, (k, _t) in enumerate(_METHOD_ITEMS) if k == cfg.method), 0)
        self._method.setCurrentIndex(cur)
        self._method.currentIndexChanged.connect(self._update_visibility)
        form.addRow(S.TFR_LBL_METHOD, self._method)

        self._fmin = QDoubleSpinBox()
        self._setup_spin(self._fmin, 0.1, self._fmax_cap - 0.1, 0.5, cfg.fmin)
        form.addRow(S.TFR_LBL_FMIN, self._fmin)

        self._fmax = QDoubleSpinBox()
        self._setup_spin(self._fmax, 0.2, self._fmax_cap, 0.5,
                         min(cfg.effective_fmax(sfreq), self._fmax_cap))
        self._fmax.setToolTip(S.TFR_DLG_NYQ_TIP.format(
            fs=self._sfreq, fmax=self._fmax_cap))
        form.addRow(S.TFR_LBL_FMAX, self._fmax)

        self._nfreq = QSpinBox()
        self._nfreq.setRange(4, 400)  # 2026-10-14 放开（原 8–120）：计算量线性、400 点仍在防抖节拍内
        self._nfreq.setValue(cfg.n_freqs)
        form.addRow(S.TFR_LBL_NFREQ, self._nfreq)

        # 按方法参数行（显隐随方法切换）
        self._ncyc = QDoubleSpinBox()
        self._setup_spin(self._ncyc, 1.0, 8.0, 0.5, cfg.n_cycles_scale)
        self._row_ncyc = self._add_form_row(form, S.TFR_LBL_NCYC, self._ncyc)

        self._tb = QDoubleSpinBox()
        self._setup_spin(self._tb, 2.0, 8.0, 1.0, cfg.time_bandwidth)
        self._row_tb = self._add_form_row(form, S.TFR_LBL_TB, self._tb)

        self._width = QDoubleSpinBox()
        self._setup_spin(self._width, 0.1, 10.0, 0.5, cfg.width)
        self._row_width = self._add_form_row(form, S.TFR_LBL_WIDTH, self._width)

        wst = QWidget()
        wst_lay = QHBoxLayout(wst)
        wst_lay.setContentsMargins(0, 0, 0, 0)
        self._win = QDoubleSpinBox()
        self._setup_spin(self._win, 0.05, 10.0, 0.05, cfg.win_s)
        self._ovl = QDoubleSpinBox()
        self._setup_spin(self._ovl, 0.0, 0.9, 0.05, cfg.overlap)
        wst_lay.addWidget(self._win)
        wst_lay.addWidget(QLabel(S.TFR_LBL_OVERLAP))
        wst_lay.addWidget(self._ovl)
        wst_lay.addStretch(1)
        self._row_wst = self._add_form_row(form, S.TFR_LBL_WIN, wst)

        # 按钮行（settings_dialog 范式：手写确定/取消）
        btns = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        lay.addLayout(btns)
        self._update_visibility()

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _setup_spin(spin: QDoubleSpinBox, lo: float, hi: float,
                    step: float, value: float) -> None:
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        spin.setValue(float(value))

    @staticmethod
    def _add_form_row(form: QFormLayout, label: str, field: QWidget) -> tuple:
        """加一行并返回 (label_widget, field)——显隐控制用."""
        form.addRow(label, field)
        row = form.rowCount() - 1
        return form.itemAt(row, QFormLayout.ItemRole.LabelRole).widget(), field

    def _update_visibility(self) -> None:
        method = self._method.currentData()
        for pair, on in (
            (self._row_ncyc, method in ("morlet", "multitaper")),
            (self._row_tb, method == "multitaper"),
            (self._row_width, method == "stockwell"),
            (self._row_wst, method == "stft"),
        ):
            for w in pair:
                w.setVisible(on)

    def _on_save(self) -> None:
        if self._fmin.value() >= self._fmax.value():
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, S.TFR_DLG_TITLE, S.TFR_DLG_BAD_RANGE)
            return
        self.accept()

    # ------------------------------------------------------------------ 对外
    def config(self) -> TfrConfig:
        """按当前控件值组装 TfrConfig（确定后调用）."""
        return TfrConfig(
            method=self._method.currentData(),
            fmin=self._fmin.value(),
            fmax=self._fmax.value(),
            n_freqs=self._nfreq.value(),
            n_cycles_scale=self._ncyc.value(),
            time_bandwidth=self._tb.value(),
            width=self._width.value(),
            win_s=self._win.value(),
            overlap=self._ovl.value(),
        )
