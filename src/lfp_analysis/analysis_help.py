"""Small offline GUI help dialog backed by the canonical help catalog."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .analysis_help_content import HELP_TOPICS, render_topic


class AnalysisHelpDialog(QtWidgets.QDialog):
    """Show a short explanation first, with detailed reading notes on demand."""

    def __init__(self, topic_id: str = "workflow", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        if topic_id not in HELP_TOPICS:
            topic_id = "workflow"
        self.setWindowTitle("LUNA 分析流程与读图说明")
        self.setMinimumSize(680, 420)
        self.resize(820, 560)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        selector_row = QtWidgets.QHBoxLayout()
        selector_row.addWidget(QtWidgets.QLabel("说明主题"))
        self.topic_combo = QtWidgets.QComboBox()
        self._topic_ids = list(HELP_TOPICS)
        for key in self._topic_ids:
            self.topic_combo.addItem(HELP_TOPICS[key]["title"], key)
        self.topic_combo.setCurrentIndex(self._topic_ids.index(topic_id))
        selector_row.addWidget(self.topic_combo, stretch=1)
        root.addLayout(selector_row)

        self.short_label = QtWidgets.QLabel()
        self.short_label.setWordWrap(True)
        self.short_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.short_label.setObjectName("analysisHelpShort")
        root.addWidget(self.short_label)

        self.detail_button = QtWidgets.QToolButton()
        self.detail_button.setText("展开详细说明")
        self.detail_button.setCheckable(True)
        self.detail_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.detail_button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        root.addWidget(self.detail_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self.detail_browser = QtWidgets.QTextBrowser()
        self.detail_browser.setOpenExternalLinks(True)
        self.detail_browser.setObjectName("analysisHelpDetails")
        self.detail_browser.hide()
        root.addWidget(self.detail_browser, stretch=1)

        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch(1)
        close_button = QtWidgets.QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        root.addLayout(close_row)

        self.topic_combo.currentIndexChanged.connect(self._update_topic)
        self.detail_button.toggled.connect(self._toggle_details)
        self._update_topic()

    def _current_topic_id(self) -> str:
        return str(self.topic_combo.currentData() or "workflow")

    def _update_topic(self, *_args: object) -> None:
        topic_id = self._current_topic_id()
        topic = HELP_TOPICS[topic_id]
        self.short_label.setText(topic["short"])
        self.detail_browser.setMarkdown(render_topic(topic_id))

    def _toggle_details(self, expanded: bool) -> None:
        self.detail_browser.setVisible(expanded)
        self.detail_button.setText("收起详细说明" if expanded else "展开详细说明")
        self.detail_button.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)
