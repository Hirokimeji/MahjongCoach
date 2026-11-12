"""Native Qt surfaces for the coaching dashboard."""
from pathlib import Path
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QLayout, QSizePolicy, QVBoxLayout, QWidget)

from strategy import normalized, risk_label, tile_name

ROOT = Path(__file__).resolve().parent
THEMES = {
    '深色': ('rgba(34,30,52,216)', 'rgba(47,42,65,209)', '#fcf8ff', '#e2d8ed', '#cbb6ff', '#332442', '#b69aec', '#ffe0a9'),
    '浅色': ('rgba(245,241,250,225)', 'rgba(253,250,255,218)', '#302a3a', '#584e63', '#695090', '#fffaff', '#72569c', '#8b481c'),
    '粉色': ('rgba(86,56,78,224)', 'rgba(77,46,69,214)', '#fff6fb', '#f8dae9', '#ffbfd8', '#502a40', '#e8a7c4', '#ffe0a9'),
}


def stylesheet(theme):
    rail, glass, ink, muted, accent, on_accent, line, warn = THEMES[theme]
    popup = {'深色':'#2f2a41','浅色':'#fdfaff','粉色':'#4d2e45'}[theme]
    return f"""
    QWidget {{ color:{ink}; font-family:'Microsoft YaHei UI'; font-size:14px; }}
    QLabel {{ background:transparent; border:0; }}
    QLabel#muted {{color:{muted};font-size:12px;}}
    QLabel#section {{font-size:18px;font-weight:700;}}
    QLabel#brand {{font-size:19px;font-weight:700;}}
    QLabel#eyebrow {{color:#e3d2ff;font-size:13px;font-weight:700;}}
    QLabel#heroTitle {{color:white;font-size:34px;font-weight:700;}}
    QLabel#heroCopy {{color:#faf4ff;font-size:14px;}}
    QLabel#alert {{color:#ffe3a8;font-size:13px;font-weight:600;}}
    QLabel#riskHigh {{color:{warn};font-weight:700;font-size:12px;}}
    QLabel#risk {{color:{ink};font-size:12px;}}
    QLabel#face {{background:#fff6ea;border-radius:4px;border-bottom:2px solid #bd9e88;}}
    QLabel#route {{color:{accent};font-weight:700;font-size:15px;}}
    QFrame#top, QFrame#rail {{background:{rail};border:0;}}
    QFrame#card {{background:{glass};border:1px solid rgba(199,179,220,100);border-radius:14px;}}
    QFrame#picked {{background:rgba(189,149,221,100);border:1px solid {accent};border-radius:6px;}}
    QPushButton {{background:{glass};color:{ink};border:1px solid rgba(199,179,220,90);
      border-radius:8px;padding:6px 12px;font-weight:600;}}
    QPushButton:hover {{border-color:{accent};}}
    QPushButton:checked {{background:{accent};color:{on_accent};border-color:{accent};}}
    QPushButton:focus {{border:2px solid {line};}}
    QPushButton:disabled {{color:{muted};}}
    QPushButton#nav {{text-align:left;padding:9px 14px;}}
    QPushButton#launch {{background:{accent};color:{on_accent};border-color:{accent};font-weight:700;}}
    QPushButton#theme {{border-radius:9px;padding:4px 8px;font-size:12px;}}
    QPushButton#caption,QPushButton#closeCaption {{background:transparent;border:0;padding:0;font-family:'Segoe UI Symbol';font-size:18px;}}
    QPushButton#caption:hover,QPushButton#caption:focus {{background:rgba(160,144,176,110);}}
    QPushButton#closeCaption:hover,QPushButton#closeCaption:focus {{background:#b64460;color:white;}}
    QDialog,QMenu,QComboBox,QListWidget,QLineEdit {{background:{rail};color:{ink};}}
    QComboBox QAbstractItemView {{background:{popup};color:{ink};selection-background-color:{accent};
      selection-color:{on_accent};border:1px solid {line};outline:0;}}
    QComboBox QAbstractItemView::item {{min-height:28px;padding:4px 10px;}}
    QListWidget::item:selected,QMenu::item:selected {{background:{accent};color:{on_accent};}}
    QScrollArea {{border:0;background:transparent;}}
    QMessageBox {{background:{rail};}}
    QScrollBar:vertical {{background:transparent;width:8px;margin:0;}}
    QScrollBar::handle:vertical {{background:{line};border-radius:4px;min-height:28px;}}
    QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
    QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}
    QToolTip {{background:#342a44;color:#fff;border:1px solid #a789c0;}}
    """


def label(text='', role='', wrap=False):
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, role='', checkable=False):
    b = QPushButton(text)
    b.setObjectName(role)
    b.setCursor(Qt.PointingHandCursor)
    b.setCheckable(checkable)
    b.clicked.connect(callback)
    return b


def panel(name='card', padding=16):
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(7)
    return frame, layout


def tile_path(code):
    if code[1] == 'z':
        stem = ['Ton','Nan','Shaa','Pei','Haku','Hatsu','Chun'][int(code[0])-1]
    else:
        stem = {'m':'Man','p':'Pin','s':'Sou'}[code[1]] + ('5-Dora' if code[0]=='0' else code[0])
    return ROOT/'tiles'/(stem+'.png')


def scaled_image(path, width, widget):
    ratio = widget.devicePixelRatioF()
    pix = QPixmap(str(path)).scaledToWidth(round(width*ratio),Qt.SmoothTransformation)
    pix.setDevicePixelRatio(ratio)
    return pix


def cover(painter, target, pix, anchor=.5):
    if pix.isNull() or target.isEmpty():
        return
    scale = max(target.width()/pix.width(), target.height()/pix.height())
    sw, sh = target.width()/scale, target.height()/scale
    source = QRectF((pix.width()-sw)*.5, (pix.height()-sh)*anchor, sw, sh)
    painter.drawPixmap(target, pix, source)

def draw_background(painter,rect,pix,portrait):
    gradient = QLinearGradient(rect.topLeft(),rect.bottomRight())
    gradient.setColorAt(0,QColor('#50425d'))
    gradient.setColorAt(1,QColor('#947c99'))
    painter.fillRect(rect,gradient)
    if portrait and not pix.isNull():
        height = rect.height()*1.05
        width = height*pix.width()/pix.height()
        center = rect.width()*.46
        painter.drawPixmap(QRectF(center-width/2,0,width,height),pix,QRectF(pix.rect()))
    else:
        cover(painter,rect,pix)


class Wallpaper(QWidget):
    def __init__(self, art):
        super().__init__()
        self.art = art.scaledToWidth(540,Qt.SmoothTransformation)
        self.theme = '深色'
        self.portrait = False
        self.mirror = True

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.save()
        if self.mirror:
            p.translate(self.width(), 0)
            p.scale(-1, 1)
        draw_background(p,QRectF(self.rect()),self.art,self.portrait)
        p.restore()
        p.fillRect(self.rect(), QColor(37,24,46,105) if self.theme=='深色' else
                   QColor(245,226,238,102) if self.theme=='浅色' else QColor(101,42,74,97))


class Hero(QWidget):
    def __init__(self, art):
        super().__init__()
        self.art = art
        box = QVBoxLayout(self)
        box.setContentsMargins(22,14,18,16)
        box.setSpacing(5)
        box.addStretch()
        self.eyebrow = label(role='eyebrow')
        box.addWidget(self.eyebrow)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.tile = label(role='face')
        row.addWidget(self.tile)
        self.title = label(role='heroTitle')
        row.addWidget(self.title)
        row.addStretch()
        box.addLayout(row)
        self.copy = label(role='heroCopy', wrap=True)
        self.alert = label(role='alert', wrap=True)
        box.addWidget(self.copy)
        box.addWidget(self.alert)
        self.setMinimumHeight(184)

    def resizeEvent(self,event):
        width = self.width()
        self.copy.setMaximumWidth(max(230, int(width * (.76 if width<550 else .58))))
        self.alert.setMaximumWidth(self.copy.maximumWidth())
        super().resizeEvent(event)

    def paintEvent(self,event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
        path = QPainterPath()
        path.addRoundedRect(rect,16,16)
        p.setClipPath(path)
        cover(p,rect,self.art,.34)
        shade = QLinearGradient(0,0,self.width(),0)
        shade.setColorAt(0,QColor(22,16,37,244))
        shade.setColorAt(.45,QColor(28,18,44,216))
        shade.setColorAt(.73,QColor(36,23,52,83))
        shade.setColorAt(1,QColor(30,20,47,18))
        p.fillPath(path, shade)
        p.setPen(QColor(200,180,223,156))
        p.drawPath(path)


class TileGrid(QWidget):
    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0,0,0,0)
        self.grid.setSpacing(3)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
        self.items = []
        self.columns = 0

    def display(self, tiles, rates=None, selected=None, threshold=5, remaining=None):
        for tile in self.items:
            self.grid.removeWidget(tile)
            tile.hide()
            tile.deleteLater()
        self.items.clear()
        for code in tiles:
            frame = QFrame()
            frame.setFixedWidth(45)
            if code == selected:
                frame.setObjectName('picked')
                selected = None
            col = QVBoxLayout(frame)
            col.setContentsMargins(2,3,2,2)
            col.setSpacing(1)
            face = label(role='face')
            face.setAlignment(Qt.AlignCenter)
            face.setPixmap(scaled_image(tile_path(code),34,self))
            col.addWidget(face,0,Qt.AlignHCenter)
            rate = rates.get(normalized(code)) if rates is not None else None
            caption = risk_label(rate) if rates is not None else tile_name(code)
            if remaining is not None:
                caption = f'{remaining[code]} 张'
            info = label(caption, 'riskHigh' if rate is not None and rate>=threshold else 'risk')
            info.setAlignment(Qt.AlignCenter)
            col.addWidget(info)
            frame.setToolTip(tile_name(code) + (' · 放铳风险 '+caption if rates is not None else ''))
            self.items.append(frame)
        self.columns = 0
        self.arrange()

    def arrange(self):
        cols = max(1,(self.width()+3)//48)
        if cols != self.columns:
            self.columns = cols
            for i, item in enumerate(self.items):
                self.grid.addWidget(item, i//cols,i%cols)
                item.show()
        # Newly reparented tiles can still be hidden when the layout is queried.
        # Calculate the row height from the tiles instead of caching an empty grid.
        for item in self.items:
            item.ensurePolished()
        rows = (len(self.items)+cols-1)//cols
        row_height = max((item.sizeHint().height() for item in self.items),default=0)
        self.grid.invalidate()
        self.setFixedHeight(rows*row_height+max(0,rows-1)*self.grid.spacing())

    def resizeEvent(self, event):
        self.arrange()
        super().resizeEvent(event)
