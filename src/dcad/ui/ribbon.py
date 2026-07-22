"""A ribbon-style toolbar: tabs of labeled button groups, in the shape of
SpaceClaim's real UI paradigm (not a copy of its artwork/assets -- original
layout code, no traced icons or branding).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabBar, QStackedWidget, QToolButton, QFrame, QSizePolicy, QScrollArea


class RibbonGroup(QFrame):
    """A labeled cluster of tool buttons, e.g. "Edit" or "Combine"."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbonGroup")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 2)
        outer.setSpacing(2)

        self._row = QWidget(self)
        self._row_layout = QHBoxLayout(self._row)
        self._row_layout.setContentsMargins(0, 0, 0, 0)
        self._row_layout.setSpacing(4)
        outer.addWidget(self._row, 1)

        label = QLabel(title, self)
        label.setObjectName("ribbonGroupLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(label)

    def add_action(self, action) -> QToolButton:
        button = QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setMinimumSize(76, 50)
        button.setAutoRaise(True)
        self._row_layout.addWidget(button)
        return button

    def add_stretch(self):
        self._row_layout.addStretch(1)


class RibbonTab(QWidget):
    """One ribbon page: a horizontal row of RibbonGroups."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(2)
        self._layout.addStretch(1)

    def add_group(self, title: str) -> RibbonGroup:
        group = RibbonGroup(title, self)
        self._layout.insertWidget(self._layout.count() - 1, group)
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("ribbonSeparator")
        self._layout.insertWidget(self._layout.count() - 1, sep)
        return group


class RibbonBar(QWidget):
    """Tab bar + stacked group pages, with a File button pinned to the left
    (SpaceClaim's own ribbon has a colored File button before its tabs)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbonBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 2, 4, 0)
        header_layout.setSpacing(0)

        self.file_button = QToolButton(self)
        self.file_button.setText("File")
        self.file_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.file_button.setObjectName("ribbonFileButton")
        self.file_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header_layout.addWidget(self.file_button)

        self.tab_bar = QTabBar(self)
        self.tab_bar.setObjectName("ribbonTabBar")
        self.tab_bar.setExpanding(False)
        header_layout.addWidget(self.tab_bar)
        header_layout.addStretch(1)
        layout.addWidget(header)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("ribbonStack")
        layout.addWidget(self.stack)

        self.tab_bar.currentChanged.connect(self.stack.setCurrentIndex)

    def add_tab(self, title: str) -> RibbonTab:
        page = RibbonTab(self)
        scroll = QScrollArea(self)
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(78)
        self.tab_bar.addTab(title)
        self.stack.addWidget(scroll)
        return page

    def set_current_tab(self, index: int):
        self.tab_bar.setCurrentIndex(index)
