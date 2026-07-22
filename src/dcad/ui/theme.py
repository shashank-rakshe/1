"""A light, blue-accented QSS theme approximating SpaceClaim's general look
(white ribbon, light-gray body, blue selection/active accents). Colors and
layout only -- no copied artwork or branding."""

ACCENT = "#0B5FA5"
ACCENT_LIGHT = "#D6E8FA"
BODY_BG = "#EDEDED"
RIBBON_BG = "#FAFAFA"
BORDER = "#D0D0D0"

STYLESHEET = f"""
QMainWindow {{
    background: {BODY_BG};
}}

#ribbonBar, #ribbonBar QWidget {{
    background: {RIBBON_BG};
}}

#ribbonFileButton {{
    background: {ACCENT};
    color: white;
    font-weight: 600;
    padding: 6px 14px;
    border: none;
}}
#ribbonFileButton:hover {{
    background: #0E75C8;
}}

QTabBar#ribbonTabBar::tab {{
    background: transparent;
    padding: 6px 14px;
    color: #333;
}}
QTabBar#ribbonTabBar::tab:selected {{
    color: {ACCENT};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT};
}}
QTabBar#ribbonTabBar::tab:hover {{
    background: {ACCENT_LIGHT};
}}

#ribbonStack {{
    border-top: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
}}

#ribbonGroup {{
    background: transparent;
}}

#ribbonGroupLabel {{
    color: #666;
    font-size: 10px;
}}

#ribbonSeparator {{
    color: {BORDER};
}}

QToolButton {{
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 2px;
    color: #222;
}}
QToolButton:hover {{
    background: {ACCENT_LIGHT};
    border: 1px solid {ACCENT};
}}
QToolButton:checked {{
    background: {ACCENT_LIGHT};
    border: 1px solid {ACCENT};
    color: {ACCENT};
}}
QToolButton:pressed {{
    background: #BFDCF5;
}}

QTreeWidget {{
    background: white;
    border: 1px solid {BORDER};
}}
QTreeWidget::item:selected {{
    background: {ACCENT_LIGHT};
    color: {ACCENT};
}}

QDockWidget {{
    titlebar-close-icon: none;
}}
QDockWidget::title {{
    background: {RIBBON_BG};
    padding: 4px;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}

QStatusBar {{
    background: {RIBBON_BG};
    border-top: 1px solid {BORDER};
}}
"""
