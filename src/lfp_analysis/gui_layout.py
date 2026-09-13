"""Reusable Qt layout helpers for result pages.

These helpers deliberately contain no analysis logic.  They keep plot controls
outside the scrolling viewport and prevent accidental mouse-wheel edits on
unfocused parameter controls.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class PlotScrollArea(QtWidgets.QScrollArea):
    """A vertically scrollable plot viewport with restorable position."""

    def __init__(
        self,
        content: QtWidgets.QWidget | None = None,
        *,
        minimum_content_height: int = 0,
        allow_horizontal: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("plotScrollArea")
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if allow_horizontal
            else QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        if content is not None:
            self.set_content(content, minimum_content_height=minimum_content_height)

    def set_content(self, content: QtWidgets.QWidget, *, minimum_content_height: int = 0) -> None:
        if minimum_content_height > 0:
            content.setMinimumHeight(int(minimum_content_height))
        content.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self.setWidget(content)

    def scroll_position(self) -> tuple[int, int]:
        return self.horizontalScrollBar().value(), self.verticalScrollBar().value()

    def restore_scroll_position(self, position: tuple[int, int]) -> None:
        """Restore after Qt has processed geometry changes, clamped to bounds."""

        horizontal, vertical = position

        def restore() -> None:
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(max(hbar.minimum(), min(int(horizontal), hbar.maximum())))
            vbar.setValue(max(vbar.minimum(), min(int(vertical), vbar.maximum())))

        QtCore.QTimer.singleShot(0, restore)

    def reset_position(self) -> None:
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().minimum())
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())


class AdaptiveStackedWidget(QtWidgets.QStackedWidget):
    """A stacked panel whose size follows the currently visible page.

    Qt's default stacked-layout size hint can be influenced by the largest
    page.  That is undesirable for method-specific parameter panels: a hidden
    Welch page must not reserve space while Multitaper is selected, and vice
    versa.  The widgets remain allocated (so user-entered values survive a
    method switch), but the container reports only the current page's size.
    """

    def _current_size_hint(self, minimum: bool = False) -> QtCore.QSize:
        current = self.currentWidget()
        if current is None:
            return QtCore.QSize(0, 0)
        return current.minimumSizeHint() if minimum else current.sizeHint()

    def sizeHint(self) -> QtCore.QSize:
        return self._current_size_hint()

    def minimumSizeHint(self) -> QtCore.QSize:
        return self._current_size_hint(minimum=True)

    def setCurrentIndex(self, index: int) -> None:
        super().setCurrentIndex(index)
        self.updateGeometry()


class WheelFocusGuard(QtCore.QObject):
    """Ignore wheel changes on unfocused spin boxes and combo boxes."""

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        guarded = isinstance(watched, (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox))
        if guarded and event.type() == QtCore.QEvent.Type.Wheel and not watched.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(watched, event)


def install_wheel_focus_guard(root: QtWidgets.QWidget) -> WheelFocusGuard:
    """Install one persistent wheel guard on all current parameter controls."""

    guard = WheelFocusGuard(root)
    controls = root.findChildren(QtWidgets.QAbstractSpinBox) + root.findChildren(QtWidgets.QComboBox)
    for control in controls:
        control.installEventFilter(guard)
    return guard
