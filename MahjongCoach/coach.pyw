"""Steam Mahjong Soul coaching window."""
import codecs
import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
import sys

from PySide6.QtCore import Qt, QTimer, QProcess, QPoint, QEvent, QRectF, QSettings
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PySide6.QtWidgets import (QApplication, QBoxLayout, QHBoxLayout, QInputDialog, QMainWindow, QMenu, QPushButton, QMessageBox,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

import backend
from backgrounds import BackgroundPlayer, Collection, DEFAULT, Gallery
from presenter import opponent_rows, present
from connection_settings import edit_connection
from strategy import MODES, normalized, risk_label, tile_name
from studio import (ROOT, THEMES, Hero, TileGrid, Wallpaper, button, label, panel, scaled_image, stylesheet, tile_path)


class ResizeGrip(QWidget):
    bottom_height = 20
    bottom_corner_width = 34

    def __init__(self,window,x,y):
        super().__init__(window)
        self.dx,self.dy = x,y
        self.origin = None
        self.setCursor(Qt.SizeFDiagCursor if x*y==1 else Qt.SizeBDiagCursor if x*y==-1
                       else Qt.SizeHorCursor if x else Qt.SizeVerCursor)
        if y==1 and x:
            self.setToolTip('拖动调整窗口大小')
            self.setAccessibleName('左下角调整大小' if x<0 else '右下角调整大小')

    def paintEvent(self,event):
        if self.dy!=1 or not self.dx:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(THEMES[self.window().theme][2])
        color.setAlpha(185)
        painter.setPen(QPen(color,2,Qt.SolidLine,Qt.RoundCap))
        if self.dx<0:
            painter.translate(self.width(),0)
            painter.scale(-1,1)
        for length in (5,10):
            painter.drawLine(self.width()-7-length,self.height()-6,
                             self.width()-7,self.height()-6-length)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.origin = event.globalPosition().toPoint()
            self.initial = self.window().geometry()
            self.grabMouse()
            event.accept()

    def mouseMoveEvent(self,event):
        if self.origin is None:
            return
        self.resize_to(event.globalPosition().toPoint())

    def resize_to(self,point):
        delta = point-self.origin
        g,w = self.initial,self.window()
        width = max(w.minimumWidth(),g.width()+self.dx*delta.x())
        height = max(w.minimumHeight(),g.height()+self.dy*delta.y())
        w.setGeometry(g.x()+(g.width()-width if self.dx<0 else 0),
                      g.y()+(g.height()-height if self.dy<0 else 0),width,height)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.origin is not None:
            self.resize_to(event.globalPosition().toPoint())
            self.origin = None
            self.releaseMouse()


class Coach(QMainWindow):
    def __init__(self):
        super().__init__()
        self.strategy = 'speed'
        self.appearance = QSettings(str(ROOT/'外观.ini'), QSettings.IniFormat)
        saved_theme = self.appearance.value('theme', '深色', type=str)
        self.theme = saved_theme if saved_theme in THEMES else '深色'
        self.risk_threshold = self.appearance.value('riskThreshold', 5, type=int)
        self.coach_only = self.appearance.value('coachOnly', True, type=bool)
        self.update_pending = False
        self.demo = self.closing = False
        self.process = self.action = self.last_error = None
        self.latest = {'kind':'connected'}
        self.demo_hand = json.loads((ROOT/'demo.json').read_text(encoding='utf-8'))
        self.normal_size = None
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setWindowTitle('雀魂 · 新手教练')
        self.setWindowIcon(QIcon(str(ROOT/'coach-portrait.png')))
        self.setMinimumSize(450, 390)
        area = self.screen().availableGeometry()
        self.resize(min(1150, area.width()-32), min(820, area.height()-54))
        art = QPixmap(str(DEFAULT.file))
        self.wall = Wallpaper(art)
        self.setCentralWidget(self.wall)
        whole = QVBoxLayout(self.wall)
        whole.setContentsMargins(0,0,0,ResizeGrip.bottom_height)
        whole.setSpacing(0)
        self.top, top_box = panel('top', 0)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(12,7,6,7)
        top_row.setSpacing(4)
        top_box.addLayout(top_row)
        self.brand = label('雀魂  /  新手教练', 'brand')
        top_row.addWidget(self.brand)
        top_row.addStretch()
        self.themes = {}
        for name in THEMES:
            b = button(name, lambda checked=False,k=name: self.set_theme(k), 'theme', True)
            self.themes[name] = b
            top_row.addWidget(b)
        self.theme_menu = QMenu(self)
        self.theme_menu.addAction('连接设置',self.open_connection)
        for name in THEMES:
            self.theme_menu.addAction(name, lambda checked=False,k=name: self.set_theme(k))
        self.theme_picker = button('主题', self.show_theme_menu, 'theme')
        top_row.addWidget(self.theme_picker)
        self.pin = button('置顶', self.set_pin, checkable=True)
        self.small = button('小窗', self.toggle_size)
        top_row.addWidget(self.pin)
        top_row.addWidget(self.small)
        top_row.addSpacing(4)
        self.minimize_button = button('−', self.showMinimized, 'caption')
        self.maximize_button = button('□', self.toggle_maximize, 'caption')
        self.close_button = button('×', self.close, 'closeCaption')
        for control, name in [(self.minimize_button,'最小化'),(self.maximize_button,'最大化'),(self.close_button,'关闭')]:
            control.setFixedSize(30,29)
            control.setAccessibleName(name)
            control.setToolTip(name)
            top_row.addWidget(control)
        whole.addWidget(self.top)

        self.monitor, monitor_layout = panel('rail', 8)
        monitor_row = QHBoxLayout()
        self.monitor_title = label('牌桌速览', 'route')
        monitor_row.addWidget(self.monitor_title)
        monitor_row.addStretch()
        monitor_row.addWidget(button('风险提醒设置', self.adjust_risk, 'theme'))
        monitor_layout.addLayout(monitor_row)
        self.monitor_risk = label(wrap=True)
        self.monitor_waits = label(wrap=True)
        monitor_layout.addWidget(self.monitor_risk)
        monitor_layout.addWidget(self.monitor_waits)
        self.monitor_opponents = label(role='muted',wrap=True)
        monitor_layout.addWidget(self.monitor_opponents)
        self.monitor_placement = label(role='route',wrap=True)
        monitor_layout.addWidget(self.monitor_placement)
        whole.addWidget(self.monitor)

        split = QHBoxLayout()
        split.setSpacing(0)
        whole.addLayout(split,1)
        self.rail, nav = panel('rail',14)
        self.rail.setFixedWidth(185)
        split.addWidget(self.rail)
        profile = QHBoxLayout()
        avatar = label()
        avatar.setPixmap(scaled_image(ROOT/'coach-portrait.png',44,self))
        profile.addWidget(avatar)
        identity = QVBoxLayout()
        identity.addWidget(label('雀魂 Steam'))
        self.status = label('已停止','muted',True)
        identity.addWidget(self.status)
        profile.addLayout(identity,1)
        nav.addLayout(profile)
        nav.addSpacing(13)
        nav.addWidget(label('牌局','muted'))
        self.live = button('实时牌局', lambda: self.select_demo(False),'nav',True)
        self.preview = button('示例手牌', lambda: self.select_demo(True),'nav',True)
        nav.addWidget(self.live)
        nav.addWidget(self.preview)
        nav.addSpacing(13)
        nav.addWidget(label('本局分析','muted'))
        nav.addWidget(button('手牌风险',lambda: self.scroll.ensureWidgetVisible(self.hand_card),'nav'))
        nav.addWidget(button('役种方向',lambda: self.scroll.ensureWidgetVisible(self.route_card),'nav'))
        nav.addWidget(button('背景收藏',self.open_backgrounds,'nav'))
        nav.addWidget(button('保存角色皮肤',self.save_skins,'nav'))
        nav.addStretch()
        self.release_status = label('', 'muted', True)
        nav.addWidget(self.release_status)
        nav.addWidget(button('使用说明',self.open_guide))
        nav.addWidget(button('连接设置',self.open_connection))
        self.launch = button('启动雀魂',self.toggle, 'launch')
        self.only_button = button('',self.set_coach_only,checkable=True)
        nav.addWidget(self.only_button)
        nav.addWidget(self.launch)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        split.addWidget(self.scroll,1)
        self.body = QWidget()
        self.scroll.setWidget(self.body)
        self.body.setAutoFillBackground(False)
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(18,15,18,15)
        self.content.setSpacing(10)
        self.mobile = QWidget()
        mobile = QHBoxLayout(self.mobile)
        mobile.setContentsMargins(0,0,0,0)
        self.m_status = label('', 'muted', True)
        mobile.addWidget(self.m_status,1)
        self.m_preview = button('示例手牌',lambda: self.select_demo(not self.demo))
        self.m_launch = button('启动雀魂',self.toggle,'launch')
        mobile.addWidget(self.m_preview)
        mobile.addWidget(self.m_launch)
        self.content.addWidget(self.mobile)
        self.hero = Hero(art)
        self.content.addWidget(self.hero)
        self.modes = {}
        mode_row = QHBoxLayout()
        mode_row.setSpacing(7)
        self.content.addLayout(mode_row)
        for key, name in MODES.items():
            b = button(name,lambda checked=False,k=key:self.switch_mode(k),checkable=True)
            self.modes[key] = b
            mode_row.addWidget(b,1)
        self.hand_card, hand = panel()
        head = QHBoxLayout()
        head.addWidget(label('手牌风险','section'))
        head.addStretch()
        head.addWidget(button('怎么看',self.details,'theme'))
        hand.addLayout(head)
        self.hand_grid = TileGrid()
        hand.addWidget(self.hand_grid)
        self.risk = label(role='muted',wrap=True)
        hand.addWidget(self.risk)
        self.content.addWidget(self.hand_card)
        self.opponent_card, seats = panel()
        seat_head = QHBoxLayout()
        seat_head.addWidget(label('各家听牌与危险牌','section'))
        seat_head.addStretch()
        self.all_tiles = button('看全部牌种',self.render_opponents,'theme',True)
        seat_head.addWidget(self.all_tiles)
        seats.addLayout(seat_head)
        self.opponent_caption = label(role='muted',wrap=True)
        seats.addWidget(self.opponent_caption)
        self.opponent_labels = []
        for _ in range(3):
            seat, tiles = label(role='route',wrap=True), label(wrap=True)
            seats.addWidget(seat)
            seats.addWidget(tiles)
            self.opponent_labels.append((seat,tiles))
        self.content.addWidget(self.opponent_card)
        self.bottom = QBoxLayout(QBoxLayout.LeftToRight)
        self.bottom.setSpacing(10)
        self.content.addLayout(self.bottom)
        self.route_card, routes = panel()
        routes.addWidget(label('役种方向','section'))
        self.route_labels = []
        for _ in range(2):
            title, guide = label(role='route'), label(wrap=True)
            routes.addWidget(title)
            routes.addWidget(guide)
            self.route_labels.append((title,guide))
        routes.addStretch()
        self.wait_card, waits = panel()
        self.wait_title = label('有效进张','section')
        waits.addWidget(self.wait_title)
        self.wait_grid = TileGrid()
        waits.addWidget(self.wait_grid)
        self.wait_caption = label(role='muted',wrap=True)
        waits.addWidget(self.wait_caption)
        self.chance = label(role='route',wrap=True)
        waits.addWidget(self.chance)
        waits.addStretch()
        self.bottom.addWidget(self.route_card,1)
        self.bottom.addWidget(self.wait_card,1)
        self.progress = label('', 'muted',True)
        self.content.addWidget(self.progress)
        self.progress.hide()
        self.mobile_guide = button('使用说明', self.open_guide)
        self.mobile_skins = button('保存角色皮肤',self.save_skins)
        foot = QHBoxLayout()
        foot.addWidget(self.mobile_guide)
        foot.addWidget(self.mobile_skins)
        self.mobile_only = button('',self.set_coach_only,checkable=True)
        self.content.insertWidget(1,self.mobile_only)
        self.set_coach_only(self.coach_only, persist=False)
        foot.addStretch()
        self.content.addLayout(foot)
        self.mobile_backgrounds = button('背景收藏',self.open_backgrounds)
        mobile.insertWidget(1,self.mobile_backgrounds)
        self.content.addStretch()
        self.set_theme(self.theme, persist=False)
        self.responsive()
        self.render(self.latest)
        self.collection = Collection()
        self.player = BackgroundPlayer(self)
        self.player.frame.connect(self.background_frame)
        self.player.failed.connect(self.background_failed)
        self.grips = [ResizeGrip(self,x,y) for x,y in (
            (-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1))]
        self.layout_grips()
        self.active_art = DEFAULT
        self.choose_background(self.collection.selected(),persist=False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(450)

    def set_theme(self,name,persist=True):
        self.theme = self.wall.theme = name
        self.setStyleSheet(stylesheet(name))
        for k,b in self.themes.items():
            b.setChecked(k==name)
        self.wall.update()
        if persist:
            self.appearance.setValue('theme',name)
            self.appearance.sync()
            if self.appearance.status()!=QSettings.NoError:
                QMessageBox.warning(self,'配色保存失败','本次配色已应用，但无法写入外观设置。')

    def set_pin(self, enabled):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        self.show()

    def show_theme_menu(self):
        self.theme_menu.popup(self.theme_picker.mapToGlobal(QPoint(0,self.theme_picker.height())))

    def open_backgrounds(self):
        dialog = Gallery(self.collection,self.active_art.key,self)
        if dialog.exec():
            key = dialog.list.currentItem().data(Qt.UserRole)
            self.choose_background(self.collection.entries[key])
        dialog.deleteLater()

    def save_skins(self):
        try:
            count = backend.save_skin_choices()
        except (OSError,ValueError,KeyError,TypeError,AttributeError,backend.yaml.YAMLError) as error:
            QMessageBox.warning(self,'保存角色皮肤',str(error))
            return
        QMessageBox.information(self,'保存角色皮肤',f'已保存当前角色和 {count} 位角色的皮肤。下次从教练启动时会自动恢复这套搭配。')

    def choose_background(self,entry,persist=True):
        self.next_art = entry
        self.commit_art = persist
        self.player.play(entry)

    def background_frame(self,pix):
        if pix.isNull():
            return
        entry = self.next_art
        portrait = entry.kind=='model' and not entry.asset
        self.wall.portrait = portrait
        self.wall.mirror = entry==DEFAULT
        self.wall.art = pix if entry.kind=='video' else pix.scaledToWidth(min(pix.width(),760),Qt.SmoothTransformation)
        self.wall.update()
        self.active_art = entry
        if self.commit_art:
            self.commit_art = False
            try:
                self.collection.remember(entry.key)
                if entry.kind=='model':
                    pix.scaledToHeight(120,Qt.SmoothTransformation).save(str(entry.file.parent/'preview.png'))
            except OSError as error:
                self.progress.setText('背景已应用，但未能保存选择：'+str(error))
                self.progress.show()

    def background_failed(self,message):
        if self.next_art!=DEFAULT:
            self.choose_background(DEFAULT,persist=False)
        self.progress.setText('背景播放失败。'+message)
        self.progress.show()
        if self.isVisible():
            QTimer.singleShot(0,lambda:QMessageBox.warning(self,'背景播放失败',message))

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.WindowStateChange and hasattr(self,'maximize_button'):
            player = getattr(getattr(self,'player',None),'video',None)
            if player:
                player.pause() if self.isMinimized() else player.play()
            self.update_window_shape()
            name = '还原' if self.isMaximized() else '最大化'
            self.maximize_button.setText('❐' if self.isMaximized() else '□')
            self.maximize_button.setAccessibleName(name)
            self.maximize_button.setToolTip(name)

    def nativeEvent(self,event_type,message):
        if event_type==b'windows_generic_MSG' and hasattr(self,'top'):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message==0x0084:  # WM_NCHITTEST: Windows needs physical client coordinates.
                point = wintypes.POINT(ctypes.c_short(msg.lParam & 0xffff).value,
                                       ctypes.c_short((msg.lParam >> 16) & 0xffff).value)
                if ctypes.windll.user32.ScreenToClient(wintypes.HWND(msg.hWnd),ctypes.byref(point)):
                    scale = self.devicePixelRatioF()
                    pos = QPoint(int(point.x/scale),int(point.y/scale))
                    if self.rect().contains(pos):
                        if isinstance(self.childAt(pos),ResizeGrip):
                            return True,1  # HTCLIENT lets Qt deliver the drag to the grip.
                        if self.top.rect().contains(self.top.mapFrom(self,pos)):
                            if not isinstance(self.childAt(pos), QPushButton):
                                return True,2  # HTCAPTION: native window dragging.
            elif msg.message==0x00a3 and msg.wParam==2:  # WM_NCLBUTTONDBLCLK on the bar.
                self.toggle_maximize()
                return True,0
        return super().nativeEvent(event_type,message)

    def responsive(self):
        compact = self.width() < 850
        narrow = self.width() < 665
        self.brand.setText('新手教练' if narrow else '雀魂  /  新手教练')
        self.theme_picker.setVisible(narrow)
        for b in self.themes.values():
            b.setVisible(not narrow)
        self.rail.setVisible(not compact)
        self.mobile.setVisible(compact)
        self.mobile_guide.setVisible(compact)
        self.mobile_skins.setVisible(compact)
        self.mobile_only.setVisible(compact)
        self.small.setText('大窗' if compact else '小窗')
        self.bottom.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)
        self.hero.setMinimumHeight(164 if compact else 192)
        self.content.setContentsMargins(10 if compact else 18,12,10 if compact else 18,12)

    def update_window_shape(self):
        self.layout_grips()
        if self.isMaximized() or self.isFullScreen():
            self.wall.layout().setContentsMargins(0,0,0,0)
            self.clearMask()
        else:
            self.wall.layout().setContentsMargins(0,0,0,ResizeGrip.bottom_height)
            outline = QPainterPath()
            outline.addRoundedRect(QRectF(self.rect()),10,10)
            self.setMask(QRegion(outline.toFillPolygon().toPolygon()))

    def layout_grips(self):
        w,h = self.width(),self.height()
        edge,corner = 7,15
        for grip in getattr(self,'grips',()):
            x,y = grip.dx,grip.dy
            # Give the two lower corners their own visible strip below the
            # scroll area and buttons, inside the rounded window region.
            if y:
                span = ResizeGrip.bottom_corner_width if y>0 else corner
                gw = span if x else w-2*span
                gh = ResizeGrip.bottom_height if y>0 else corner if x else edge
                left = 0 if x<0 else w-gw if x>0 else span
                grip.setGeometry(left,h-gh if y>0 else 0,gw,gh)
            else:
                grip.setGeometry(0 if x<0 else w-edge,corner,edge,h-corner-ResizeGrip.bottom_height)
            grip.setVisible(not (self.isMaximized() or self.isFullScreen()))
            grip.raise_()

    def showEvent(self,event):
        super().showEvent(event)
        self.update_window_shape()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_window_shape()
        if hasattr(self,'mobile_guide'):
            self.responsive()

    def toggle_size(self):
        area = self.screen().availableGeometry()
        if self.width() >= 850:
            self.normal_size = self.size()
            self.showNormal()
            self.resize(min(550,area.width()-16),min(660,area.height()-40))
        elif self.normal_size:
            self.resize(self.normal_size.boundedTo(area.size()))
        else:
            self.resize(min(1150,area.width()-16),min(820,area.height()-40))

    @staticmethod
    def open_guide():
        os.startfile(str(ROOT/'使用说明.md'))

    def open_connection(self):
        if self.process or self.needs_restore():
            QMessageBox.information(self,'连接设置','请先停止并恢复，再修改连接设置。')
            return
        edit_connection(self)

    def switch_mode(self,key):
        self.strategy = key
        self.render(self.latest)

    def set_coach_only(self, enabled, persist=True):
        self.coach_only = enabled
        for b in (self.only_button,self.mobile_only):
            b.setChecked(enabled)
            b.setText('全解锁关闭 · 仅辅助' if enabled else '外观沿用 MAX 设置')
            b.setToolTip('点击切换。仅辅助会关闭外观插件，保留打牌提示。请在启动前切换。')
        if persist:
            self.appearance.setValue('coachOnly',enabled)
            self.appearance.sync()

    def render_opponents(self, *_):
        active = bool(self.view['hand'])
        self.opponent_card.setVisible(active)
        if not active:
            return
        all_tiles = self.all_tiles.isChecked()
        rows = opponent_rows(self.latest,hand_only=not all_tiles)
        scope = '全部牌种' if all_tiles else '我的手牌'
        self.opponent_caption.setText(f'{scope}中，列出估计最容易让各家荣和的三种牌。牌名旁的百分比已计入该家听牌的可能。'
                                     if rows else '等待各家牌河信息。')
        self.monitor_opponents.setText('听牌  '+'　'.join(f'{seat} {rate}' for seat,rate,_ in rows) if rows else '')
        self.monitor_opponents.setVisible(bool(rows))
        for i,(title,tiles) in enumerate(self.opponent_labels):
            title.setVisible(i < len(rows))
            tiles.setVisible(i < len(rows))
            if i < len(rows):
                seat,rate,danger = rows[i]
                title.setText(f'{seat} · 听牌 {rate}')
                tiles.setText(danger)

    def adjust_risk(self):
        value, accepted = QInputDialog.getInt(self,'风险提醒','放铳估计达到多少 % 时提醒？',
                                              self.risk_threshold,1,100)
        if accepted:
            self.risk_threshold = value
            self.appearance.setValue('riskThreshold',value)
            self.appearance.sync()
            self.render(self.latest)

    def update_monitor(self, snapshot, view):
        if snapshot.get('kind') == 'processing' and self.monitor_risk.text():
            self.monitor_title.setText('更新中 · 上次确认的牌面')
            return
        self.monitor.setVisible(bool(view['hand']))
        if not view['hand']:
            self.monitor_risk.clear()
            self.monitor_waits.clear()
            return
        title = '示例手牌' if self.demo else '实时手牌'
        if view['tile']:
            tile = view['tile']
            rate = view['rates'].get(normalized(tile))
            warning = '高风险 ' if rate is not None and rate >= self.risk_threshold else ''
            title += f' · 建议打{tile_name(tile)} · {warning}{risk_label(rate)}'
        self.monitor_title.setText(title)
        risks = []
        for tile in dict.fromkeys(view['hand']):
            rate = view['rates'].get(normalized(tile))
            high = '⚠' if rate is not None and rate >= self.risk_threshold else ''
            risks.append(f'{high}{tile_name(tile)} {risk_label(rate)}')
        self.monitor_risk.setText('放铳估计  ' + ' · '.join(risks))
        self.monitor_risk.setToolTip(view['risk_caption'])
        cut = f'打{tile_name(view["tile"])}后' if view['tile'] else '当前'
        known = ('current_waits' in snapshot or view['tile'] and (
                 normalized(view['tile']) in (snapshot.get('waits_by_cut') or {}) or
                 any(c.get('tile')==view['tile'] and 'waits' in c for c in snapshot.get('candidates',[]))))
        entries = '  '.join(f'{tile_name(w["tile"])}×{w["remaining"]}' for w in view['waits'])
        self.monitor_waits.setText(cut+'进张  '+(entries or ('没有未见的有效牌' if known else '等待可用牌面')))

    def select_demo(self, enabled):
        self.demo = enabled
        self.render(self.demo_hand if enabled else {'kind':'connected'})
        self.scroll.verticalScrollBar().setValue(0)
        if not enabled:
            self.poll()

    def render(self,snapshot):
        self.latest = snapshot
        v = self.view = present(snapshot,self.strategy,self.risk_threshold)
        self.monitor_placement.setText(v.get('placement',''))
        self.monitor_placement.setVisible(bool(v.get('placement')))
        self.update_monitor(snapshot,v)
        self.render_opponents()
        for k,b in self.modes.items():
            b.setChecked(k==self.strategy)
            if k=='avoid_last':
                b.setText('避末' if snapshot.get('players')==3 else '避四')
        self.live.setChecked(not self.demo)
        self.preview.setChecked(self.demo)
        self.m_preview.setText('返回实时' if self.demo else '示例手牌')
        source = '练习示例 · 模拟牌河' if self.demo else '实时牌局'
        if 'round' in snapshot and v['hand']:
            rnd = snapshot['round']
            source += f'    /    {"东南西北"[(rnd//4)%4]} {rnd%4+1} 局'
            if snapshot.get('seat_wind'):
                source += ' · 自风'+tile_name(snapshot['seat_wind'])
        self.hero.eyebrow.setText(source)
        self.hero.title.setText(v['title'])
        self.hero.copy.setText(v['reason'].replace('看截图示例','示例手牌'))
        self.hero.alert.setText(v['note'])
        self.hero.alert.setVisible(bool(v['note']))
        self.hero.tile.setVisible(bool(v['tile']))
        if v['tile']:
            self.hero.tile.setPixmap(scaled_image(tile_path(v['tile']),40,self))
        self.hand_grid.display(v['hand'],v['rates'],v['tile'],self.risk_threshold)
        self.hand_grid.setVisible(bool(v['hand']))
        self.risk.setText(v['risk_caption'] or '发牌后，每张手牌下会显示打出它的放铳风险。')
        for i,(title,guide) in enumerate(self.route_labels):
            exists = i < len(v['routes'])
            title.setVisible(exists)
            guide.setVisible(exists or i==0)
            if exists:
                plan = v['routes'][i]
                title.setText(f'{plan.name}   ·   {plan.han} 番')
                guide.setText(plan.guide)
            elif i==0:
                guide.setText('发牌后看适合的役，以及哪些牌值得留。' if not v['hand'] else '先保留能连成组的牌，等待下一次进张。')
        self.wait_title.setText(v['next_title'])
        self.chance.setText(v['forecast'])
        self.chance.setVisible(bool(v['forecast']))
        remaining = {w['tile']:w['remaining'] for w in v['waits']}
        self.wait_grid.display(list(remaining), remaining=remaining)
        self.wait_grid.setVisible(bool(v['waits']))
        unseen = sum(w['remaining'] for w in v['waits'])
        self.wait_caption.setText(f'{len(v["waits"])} 种有效牌  ·  共 {unseen} 张未见' if v['waits'] else '有有效进张时，牌面会显示在这里。')

    def details(self):
        v = self.view
        pieces = [v['detail']] if v['detail'] else []
        if v['waits']:
            pieces.append('有效牌  ' + '、'.join(f'{tile_name(w["tile"])}（{w["remaining"]} 张未见）' for w in v['waits']))
        if v['alternatives']:
            pieces.append('其他切法\n'+'\n'.join(f'{tile_name(c["tile"])} · {c["shanten"]} 向听，{c["ukeire"]} 张有效牌' for c in v['alternatives']))
        pieces.append('放铳指别人用你打出的牌和牌。百分比根据弃牌、副露和立直信息估算，可能有偏差。开局信息不足时显示「待估」。')
        QMessageBox.information(self,'进张与风险', '\n\n'.join(pieces))

    def needs_restore(self):
        local, game = backend.read_session(), backend.max_launcher.state_read()
        return bool(local.get('active') or 'helper_enabled_before' in local or game.get('active')
                    or game.get('pid') or game.get('extension_hash'))

    def poll(self):
        if self.process:
            return
        try:
            active = self.needs_restore()
            for b in (self.only_button,self.mobile_only):
                b.setEnabled(not active)
            if self.update_pending and not active and not self.closing:
                self.update_pending = False
                self.run('update')
                return
            text = '操作未完成' if self.last_error else ('提示已开启' if active else '已停止')
            for lbl in (self.status,self.m_status):
                lbl.setText(text)
            for b in (self.launch,self.m_launch):
                b.setText('停止并恢复' if active else '启动雀魂')
            if self.demo:
                return
            snapshot = ({'kind':'error','message':self.last_error} if self.last_error else
                        backend.local_request('/state',timeout=.2) if active else {'kind':'connected'})
        except (OSError,ValueError):
            snapshot = {'kind':'error','message':'暂时无法读取本地提示服务。'}
        if snapshot != self.latest:
            self.render(snapshot)

    def toggle(self):
        if not self.process:
            if not self.needs_restore() and not backend.max_launcher.SETTINGS.exists():
                if not edit_connection(self):
                    return
            self.run('stop' if self.needs_restore() else 'start')

    def run(self,action):
        self.action = action
        if action == 'update':
            self.release_status.setText('正在检查 MAX 更新…')
            self.progress.setText(self.release_status.text())
        else:
            self.last_error, self.demo = None, False
            self.progress.setText('正在启动…' if action=='start' else '正在停止并恢复…')
            self.render({'kind':'processing'})
        self.progress.show()
        for b in (self.launch,self.m_launch,self.preview,self.live,self.m_preview):
            b.setEnabled(False)
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.buffer = ''
        p = self.process = QProcess(self)
        p.setWorkingDirectory(str(ROOT))
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self.read_output)
        p.finished.connect(self.finished)
        p.errorOccurred.connect(lambda err: self.finished(1) if err==QProcess.FailedToStart else None)
        args = ['-X','utf8',str(ROOT/'backend.py'),action]
        if action == 'start':
            self.only_button.setEnabled(False)
            self.mobile_only.setEnabled(False)
            if self.coach_only:
                args.append('--coach-only')
        p.start(sys.executable,args)

    def read_output(self,final=False):
        data = bytes(self.process.readAllStandardOutput())
        self.buffer += self.decoder.decode(data,final)
        lines = self.buffer.split('\n')
        self.buffer = '' if final else lines.pop()
        for line in lines:
            if line.strip():
                self.progress.setText(line.strip())
                if self.action == 'update':
                    self.release_status.setText(line.strip())

    def finished(self,code,*args):
        p = self.process
        if not p:
            return
        self.read_output(final=True)
        if p.error()==QProcess.FailedToStart:
            self.progress.setText(p.errorString())
        self.process = None
        p.deleteLater()
        for b in (self.launch,self.m_launch,self.preview,self.live,self.m_preview):
            b.setEnabled(True)
        if self.action == 'update':
            if code:
                self.release_status.setText('MAX 更新检查未完成')
                self.release_status.setToolTip(self.progress.text())
            if self.closing:
                self.close()
                return
            # Retry network failures later, recheck an open coach periodically.
            minutes = 1 if '推迟更新' in self.release_status.text() else 30 if code else 720
            QTimer.singleShot(minutes*60_000,self.schedule_update)
        elif code:
            self.last_error = self.progress.text()
            self.closing = False
        elif self.closing:
            if self.action=='stop' and self.needs_restore():
                self.closing = False
                self.last_error = '还有配置需要恢复，请重试停止。'
            else:
                self.close()
                return
        self.poll()

    def schedule_update(self):
        self.update_pending = True

    def closeEvent(self,event):
        if self.process or self.needs_restore():
            event.ignore()
            self.closing = True
            if not self.process:
                self.run('stop')
        else:
            self.player.stop()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    with (backend.MAX_ROOT/'.control.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            QMessageBox.information(None,'雀魂新手教练','教练窗口已经打开，请先关闭原窗口。')
            return
        try:
            window = Coach()
            window.schedule_update()
            window.show()
            if not backend.max_launcher.SETTINGS.exists():
                QTimer.singleShot(0,window.open_connection)
            app.exec()
        except Exception as error:
            QMessageBox.critical(None,'雀魂新手教练',str(error))


if __name__=='__main__':
    main()
