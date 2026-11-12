"""Local wallpaper collection and isolated Cubism playback."""
import json
import ctypes
import hashlib
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QRectF, QSize, Qt, QTimer, QUrl, Signal, QElapsedTimer, QSaveFile, QIODevice
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QMovie, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QListView, QMessageBox, QStyle, QStyledItemDelegate, QVBoxLayout)

from model_player import SIZE
from studio import ROOT, THEMES, button, cover, label


@dataclass(frozen=True)
class Entry:
    key: str
    name: str
    group: str
    file: Path
    kind: str
    asset: dict | None = None


DEFAULT = Entry('studio','雀室 · 樱色黄昏','内置',ROOT/'雀室.webp','image')
SCENES = '动态场景壁纸'


def cached_scene(entry):
    """Match the exact manifest version, including downloads made in MODORA."""
    asset = entry.asset
    blobs = Path(os.environ['APPDATA'])/'MODORA/IndexedDB/modora_app_0.indexeddb.blob'
    for path in (entry.file, *blobs.glob('*/*/*')):
        try:
            if path.stat().st_size != asset['size']:
                continue
            with path.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()==asset['sha256']:
                    return path
        except OSError:
            continue
    return None
def model_references(path):
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    refs = config.get('FileReferences', {})
    if config.get('Version')!=3 or not refs.get('Moc') or not refs.get('Textures'):
        raise ValueError('请选择带有 Moc 和贴图引用的 Cubism model3.json。')
    files = [refs['Moc'], *refs['Textures']]
    files.extend(refs[k] for k in ('Physics','Pose','UserData','DisplayInfo') if refs.get(k))
    for item in refs.get('Expressions', []):
        files.append(item['File'])
    for motions in refs.get('Motions', {}).values():
        for motion in motions:
            files.append(motion['File'])
            if motion.get('Sound'):
                files.append(motion['Sound'])
    base = path.parent.resolve()
    result = []
    for name in dict.fromkeys(files):
        rel = Path(name)
        src = (base/rel).resolve()
        if rel.anchor or '..' in rel.parts or ':' in name or not src.is_relative_to(base):
            raise ValueError(f'无效的模型资源路径：{name}')
        result.append((src,rel))
    return result


def model_files(path):
    result = model_references(path)
    for src,rel in result:
        if not src.is_file():
            raise ValueError(f'模型缺少资源：{rel}')
    with result[0][0].open('rb') as f:
        if f.read(4)!=b'MOC3':
            raise ValueError('模型数据缺少 MOC3 文件头。')
    return result


class Collection:
    def __init__(self, folder=None):
        self.folder = folder or ROOT/'背景收藏'
        self.state = self.folder/'selection.json'
        self.entries = {DEFAULT.key:DEFAULT}
        for asset in json.loads((ROOT/'场景壁纸目录.json').read_text(encoding='utf-8')):
            slug = asset['id']
            entry = Entry('scene-'+slug,asset['name'],SCENES,self.folder/'场景壁纸'/slug/'wallpaper.mp4','video',asset)
            self.entries[entry.key] = entry
        catalogue = json.loads((ROOT/'碧蓝航线目录.json').read_text(encoding='utf-8'))
        self.base = catalogue['base']
        for slug, asset in catalogue['models'].items():
            key = 'azur-'+slug
            path = self.folder/'碧蓝航线'/slug/Path(asset['model']).name
            self.entries[key] = Entry(key,asset['name'],'碧蓝航线 Live2D',path,'model',asset)
        for manifest in sorted(self.folder.glob('*/item.json')):
            try:
                item = json.loads(manifest.read_text(encoding='utf-8'))
                path = (manifest.parent/item['file']).resolve()
                if path.is_relative_to(manifest.parent.resolve()) and path.is_file():
                    key = manifest.parent.name
                    self.entries[key] = Entry(key,item['name'],'我的收藏',path,item['kind'])
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def selected(self):
        try:
            return self.entries[json.loads(self.state.read_text(encoding='utf-8'))['key']]
        except (OSError, ValueError, KeyError, TypeError):
            return DEFAULT

    def remember(self,key):
        self.folder.mkdir(parents=True,exist_ok=True)
        tmp = self.state.with_suffix('.tmp')
        tmp.write_text(json.dumps({'key':key}),encoding='utf-8')
        tmp.replace(self.state)

    def import_file(self,path):
        key = uuid.uuid4().hex
        folder = self.folder/key
        model = path.name.lower().endswith('.model3.json')
        if model:
            deps = model_files(path)
            kind, filename = 'model','model.model3.json'
        else:
            reader = QImageReader(str(path))
            if not reader.canRead() or reader.read().isNull():
                raise ValueError('无法读取这张图片，请使用 PNG、JPEG、WebP 或 GIF。')
            kind = 'animation' if reader.supportsAnimation() and reader.imageCount()!=1 else 'image'
            filename = 'image'+path.suffix.lower()
        name = path.name[:-len('.model3.json')] if model else path.stem
        folder.mkdir(parents=True)
        try:
            if model:
                for source,rel in deps:
                    (folder/rel).parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,folder/rel)
            shutil.copyfile(path,folder/filename)
            (folder/'item.json').write_text(json.dumps(dict(name=name,file=filename,kind=kind),
                                           ensure_ascii=False),encoding='utf-8')
        except Exception:
            shutil.rmtree(folder)
            raise
        entry = Entry(key,name,'我的收藏',folder/filename,kind)
        self.entries[key] = entry
        return entry


class CoverCard(QStyledItemDelegate):
    cell = QSize(276,188)

    def sizeHint(self,option,index):
        return self.cell

    def paint(self,painter,option,index):
        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        theme = self.parent().window().parent().theme
        _,_,ink,_,accent,_,line,_ = THEMES[theme]
        rect = QRectF(option.rect).adjusted(4,4,-4,-4)
        shape = QPainterPath()
        shape.addRoundedRect(rect,12,12)
        painter.setClipPath(shape, Qt.IntersectClip)
        surface = {'深色':'#3e374e','浅色':'#eae3f0','粉色':'#705267'}[theme]
        painter.fillPath(shape,QColor(surface))
        art = rect.adjusted(0,0,0,-41)
        icon = index.data(Qt.DecorationRole)
        if icon and not icon.isNull():
            pix = icon.pixmap(QSize(560,400))
            cover(painter,art,pix,.30)
        text_rect = rect.adjusted(10,art.height(),-10,0).toRect()
        painter.setPen(QColor(ink))
        text = option.fontMetrics.elidedText(index.data(),Qt.ElideRight,text_rect.width())
        painter.drawText(text_rect,Qt.AlignLeft|Qt.AlignVCenter,text)
        selected = option.state & (QStyle.State_Selected | QStyle.State_HasFocus)
        edge = QColor(accent if selected else line)
        edge.setAlpha(255 if selected else 120 if option.state & QStyle.State_MouseOver else 75)
        width = 2 if selected else 1
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(edge,width))
        painter.drawRoundedRect(rect.adjusted(width/2,width/2,-width/2,-width/2),12-width/2,12-width/2)
        painter.restore()


class Gallery(QDialog):
    def __init__(self, collection, active, parent):
        super().__init__(parent)
        self.collection = collection
        self.active = active
        self.net = QNetworkAccessManager(self)
        self.loading = False
        self.inflight = set()
        self.thumb_errors = set()
        self.visible_items = {}
        self.setWindowTitle('背景收藏')
        self.resize(640,550)
        box = QVBoxLayout(self)
        box.addWidget(label('背景收藏','section'))
        row = QHBoxLayout()
        self.group = QComboBox()
        self.group.addItems([SCENES,'碧蓝航线 Live2D','内置','我的收藏','全部'])
        row.addWidget(self.group)
        row.addStretch()
        self.imports = [button('导入图片 / 动图',lambda:self.browse(False)),button('导入 Live2D',lambda:self.browse(True))]
        for b in self.imports:
            row.addWidget(b)
        box.addLayout(row)
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索主题或换装，例如「奶霜茶歇」「象牙猫坊」')
        box.addWidget(self.search)
        self.list = QListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setMovement(QListView.Static)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setItemDelegate(CoverCard(self.list))
        self.list.setMouseTracking(True)
        self.list.setGridSize(CoverCard.cell)
        self.list.setWordWrap(True)
        box.addWidget(self.list,1)
        self.hint = label('', 'muted',True)
        box.addWidget(self.hint)
        self.store = button('打开 MODORA 主题商店所在应用',self.open_store)
        box.addWidget(self.store,0,Qt.AlignLeft)
        self.store.hide()
        self.cache_timer = QTimer(self)
        self.cache_timer.setInterval(1800)
        self.cache_timer.timeout.connect(self.check_store_download)
        self.apply = button('应用背景',self.prepare,'launch')
        box.addWidget(self.apply,0,Qt.AlignRight)
        self.group.currentTextChanged.connect(self.populate)
        self.search.textChanged.connect(self.populate)
        self.thumb_timer = QTimer(self)
        self.thumb_timer.setSingleShot(True)
        self.thumb_timer.timeout.connect(self.load_thumbs)
        self.list.verticalScrollBar().valueChanged.connect(lambda:self.thumb_timer.start(90))
        self.list.currentItemChanged.connect(self.selection_changed)
        self.list.itemDoubleClicked.connect(lambda *_:self.prepare())
        self.populate()

    def showEvent(self,event):
        super().showEvent(event)
        rounding = ctypes.c_uint32(2)  # DWMWCP_ROUND for the native dialog frame.
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(int(self.winId())),33,
                                                   ctypes.byref(rounding),ctypes.sizeof(rounding))
        # Match the native modal caption to the selected palette on Windows 11.
        colors = {'深色':('#272237','#fcf8ff'),'浅色':('#efeaf3','#302a3a'),'粉色':('#55394b','#fff6fb')}
        for attr,color in zip((35,36),colors[self.parent().theme]):
            value = ctypes.c_uint32(int.from_bytes(bytes.fromhex(color[1:]),'little'))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(int(self.winId())),attr,
                                                      ctypes.byref(value),ctypes.sizeof(value))
        self.thumb_timer.start(20)

    def populate(self,*_):
        self.visible_items.clear()
        self.list.clear()
        for entry in self.collection.entries.values():
            if self.group.currentText() not in ('全部',entry.group) or self.search.text().strip().lower() not in (entry.name+entry.key).lower():
                continue
            src = (entry.file.parent/'poster.jpg' if entry.kind=='video' else entry.file.parent/'painting.webp' if entry.asset else entry.file
                   if entry.kind!='model' else entry.file.parent/'preview.png')
            pix = QPixmap(str(src)) if src.is_file() else QPixmap()
            item = QListWidgetItem(QIcon(pix.scaled(320,320,Qt.KeepAspectRatio,Qt.SmoothTransformation))
                                   if not pix.isNull() else QIcon(),entry.name+(' · 动态' if entry.kind=='spine' else ''))
            item.setToolTip(entry.name)
            item.setData(Qt.UserRole,entry.key)
            self.list.addItem(item)
            self.visible_items[entry.key]=item
            if entry.key==self.active:
                self.list.setCurrentItem(item)
        if self.list.currentRow()<0 and self.list.count():
            self.list.setCurrentRow(0)
        self.selection_changed()
        self.thumb_timer.start(50)

    def fetch(self,rel,dest,callback):
        req = QNetworkRequest(QUrl(self.collection.base).resolved(QUrl(rel)))
        req.setTransferTimeout(25000)
        reply = self.net.get(req)
        def done():
            problem = ''
            try:
                if reply.error()!=QNetworkReply.NoError:
                    raise OSError(reply.errorString())
                data = bytes(reply.readAll())
                if not data:
                    raise ValueError('下载内容为空。')
                if dest.suffix.lower() in ('.png','.webp','.jpg') and QImage.fromData(data).isNull():
                    raise ValueError('贴图无法解码。')
                if dest.suffix.lower()=='.moc3' and not data.startswith(b'MOC3'):
                    raise ValueError('模型数据无效。')
                if dest.suffix.lower()=='.json':
                    json.loads(data)
                dest.parent.mkdir(parents=True,exist_ok=True)
                tmp = dest.with_name(dest.name+'.part')
                tmp.write_bytes(data)
                tmp.replace(dest)
            except (OSError,ValueError) as e:
                problem = str(e)
            reply.deleteLater()
            callback(problem)
        reply.finished.connect(done)

    def load_thumbs(self):
        if not self.isVisible():
            return
        rect = self.list.viewport().rect()
        for key,item in self.visible_items.items():
            entry = self.collection.entries[key]
            if len(self.inflight)>=4:
                break
            if not entry.asset or not item.icon().isNull() or not rect.intersects(self.list.visualItemRect(item)):
                continue
            if entry.kind=='video':
                dest = entry.file.parent/'poster.jpg'
                url = entry.asset['cover']
            else:
                dest = entry.file.parent/'painting.webp'
                slug = entry.key.removeprefix('azur-').removesuffix('_hx')
                url = 'https://raw.githubusercontent.com/iujab/azurlane-images/main/paintings/'+slug+'.webp'
            if dest in self.inflight or dest in self.thumb_errors:
                continue
            if dest.exists():
                item.setIcon(QIcon(str(dest)))
                continue
            self.inflight.add(dest)
            def loaded(error,k=key,p=dest):
                self.inflight.discard(p)
                if error:
                    self.thumb_errors.add(p)
                elif k in self.visible_items:
                    self.visible_items[k].setIcon(QIcon(str(p)))
                self.thumb_timer.start(10)
            self.fetch(url,dest,loaded)

    def prepare(self):
        item = self.list.currentItem()
        if not item or self.loading:
            return
        entry = self.collection.entries[item.data(Qt.UserRole)]
        if entry.kind=='video':
            self.prepare_scene(entry)
            return
        if not entry.asset:
            self.accept()
            return
        self.loading = True
        self.apply.setEnabled(False)
        self.list.setEnabled(False)
        self.search.setEnabled(False)
        self.group.setEnabled(False)
        for b in self.imports:
            b.setEnabled(False)
        done = []

        def advance(error=''):
            if not self.isVisible():
                return
            if not error:
                try:
                    if not entry.file.is_file():
                        self.hint.setText('正在下载模型清单 · '+entry.name)
                        self.fetch(entry.asset['model'],entry.file,advance)
                        return
                    if not done:
                        refs = model_references(entry.file)
                        done.extend((src, rel) for src, rel in refs if not src.is_file())
                    if done:
                        src, rel = done.pop()
                        self.hint.setText(f'正在下载 {rel.name} · 另有 {len(done)} 个文件')
                        remote = entry.asset['model'].rsplit('/',1)[0]+'/'+rel.as_posix()
                        self.fetch(remote,src,advance)
                        return
                    model_files(entry.file)
                    (entry.file.parent/'ready').touch()
                    self.accept()
                    return
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    error = str(exc)
            self.loading = False
            for widget in (self.list,self.apply,self.group,self.search,*self.imports):
                widget.setEnabled(True)
            self.hint.setText('下载未完成，可点击重试。'+error)
        advance()

    def open_store(self):
        exe = Path('D:/mihoyo/3dmzzz/MODORA Preview/MODORA Preview.exe')
        try:
            os.startfile(str(exe))
        except OSError as error:
            self.hint.setText('请在 MODORA 主题商店下载所选主题。'+str(error))

    def use_cached_scene(self,entry):
        source = cached_scene(entry)
        if source is None:
            return False
        if source != entry.file:
            entry.file.parent.mkdir(parents=True,exist_ok=True)
            temp = entry.file.with_name(uuid.uuid4().hex+'.part')
            try:
                shutil.copyfile(source,temp)
                with temp.open('rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=entry.asset['sha256']:
                        return False
                temp.replace(entry.file)
            finally:
                temp.unlink(missing_ok=True)
        self.cache_timer.stop()
        self.accept()
        return True

    def check_store_download(self):
        item = self.list.currentItem()
        if self.isVisible() and item:
            try:
                self.use_cached_scene(self.collection.entries[item.data(Qt.UserRole)])
            except OSError as error:
                self.cache_timer.stop()
                self.hint.setText(str(error))

    def prepare_scene(self,entry):
        self.cache_timer.stop()
        try:
            if self.use_cached_scene(entry):
                return
            entry.file.parent.mkdir(parents=True,exist_ok=True)
        except OSError as error:
            self.hint.setText(str(error))
            return
        out = QSaveFile(str(entry.file))
        if not out.open(QIODevice.WriteOnly):
            self.hint.setText(out.errorString())
            return
        self.loading = True
        controls = (self.apply,self.list,self.search,self.group,*self.imports)
        for ctrl in controls:
            ctrl.setEnabled(False)
        self.store.hide()
        self.hint.setText('正在连接壁纸商店…')
        req = QNetworkRequest(QUrl(entry.asset['video']))
        req.setTransferTimeout(30000)
        reply = self.net.get(req)
        digest = hashlib.sha256()
        size = entry.asset['size']
        received = 0
        problem = ''
        def read():
            nonlocal received,problem
            data = bytes(reply.readAll())
            if not data or problem:
                return
            received += len(data)
            if received>size or out.write(data)!=len(data):
                problem = '下载大小异常或无法写入缓存。'
                reply.abort()
                return
            digest.update(data)
            self.hint.setText(f'正在下载「{entry.name}」  {100*received//size}%')
        def finish():
            read()
            self.rejected.disconnect(reply.abort)
            error = problem or (reply.errorString() if reply.error()!=QNetworkReply.NoError else '')
            if not error and (received!=size or digest.hexdigest()!=entry.asset['sha256']):
                error = '文件与主题清单不一致'
            if not error and not out.commit():
                error = out.errorString()
            reply.deleteLater()
            self.loading = False
            if not error:
                self.accept()
                return
            out.cancelWriting()
            if self.isVisible():
                for ctrl in controls:
                    ctrl.setEnabled(True)
                self.hint.setText(f'下载未完成（{error}）。可重试，或在 MODORA 下载「{entry.name}」，完成后这里会自动应用。')
                self.store.show()
                self.cache_timer.start()
        reply.readyRead.connect(read)
        self.rejected.connect(reply.abort)
        reply.finished.connect(finish)

    def selection_changed(self,*_):
        self.cache_timer.stop()
        self.store.hide()
        item = self.list.currentItem()
        self.apply.setEnabled(item is not None)
        if not item:
            self.hint.setText('没有找到匹配的背景。')
            return
        entry = self.collection.entries[item.data(Qt.UserRole)]
        if entry.kind=='video':
            self.apply.setText('应用背景' if entry.file.is_file() else '下载并应用')
            self.hint.setText(f'{self.list.count()} 项  ·  {entry.name}  ·  {entry.asset["detail"]}')
            return
        cached = entry.asset and (entry.file.parent/'ready').is_file()
        self.apply.setText('下载并应用' if entry.asset and not cached else '应用背景')
        kind = '已缓存 · 可离线应用' if cached else '按需下载模型、贴图和动作' if entry.asset else entry.group
        self.hint.setText(f'{self.list.count()} 项  ·  {kind}')

    def browse(self,model):
        filters = 'Live2D 模型 (*.model3.json)' if model else '图片与动图 (*.png *.jpg *.jpeg *.webp *.gif *.bmp)'
        name,_ = QFileDialog.getOpenFileName(self,'选择模型入口及其同目录资源' if model else '选择背景图片','',filters)
        if not name:
            return
        try:
            entry = self.collection.import_file(Path(name))
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
            QMessageBox.warning(self,'导入失败',str(error))
            return
        self.active = entry.key
        self.search.clear()
        self.group.setCurrentText('我的收藏')
        self.populate()


class BackgroundPlayer(QObject):
    frame = Signal(QPixmap)
    failed = Signal(str)

    def __init__(self,parent):
        super().__init__(parent)
        self.proc = self.movie = self.video = None
        self.buffer = bytearray()
        self.pending = False
        self.tick = QTimer(self)
        self.tick.setInterval(50)
        self.tick.timeout.connect(self.request_frame)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(lambda:self.fail('模型没有及时返回画面，请检查模型与显卡驱动。'))

    def stop(self):
        self.timeout.stop()
        self.tick.stop()
        self.pending = False
        if self.video:
            player,self.video = self.video,None
            player.stop()
            player.setVideoSink(None)
            player.deleteLater()
        if self.movie:
            self.movie.stop()
            self.movie.setFileName('')
            self.movie.deleteLater()
            self.movie = None
        if self.proc:
            p,self.proc = self.proc,None
            p.closeWriteChannel()
            if not p.waitForFinished(250):
                p.kill()
                p.waitForFinished(1000)
            p.deleteLater()
        self.buffer.clear()

    def fail(self,message):
        self.stop()
        self.failed.emit(message)

    def play(self,entry):
        self.stop()
        if entry.kind=='video':
            player = self.video = QMediaPlayer(self)
            sink = QVideoSink(player)
            player.setVideoSink(sink)
            player.setLoops(QMediaPlayer.Infinite)
            clock = QElapsedTimer()
            def render(frame):
                if player is not self.video or not frame.isValid() or self.parent().isMinimized():
                    return
                if clock.isValid() and clock.elapsed()<30:
                    return
                clock.start()
                img = frame.toImage()
                if not img.isNull():
                    width = max(640,min(1600,self.parent().width()))
                    if img.width()>width:
                        img = img.scaledToWidth(width,Qt.SmoothTransformation)
                    self.frame.emit(QPixmap.fromImage(img))
            sink.videoFrameChanged.connect(render)
            player.errorOccurred.connect(lambda *args:self.fail('视频播放失败：'+player.errorString()) if player is self.video else None)
            player.setSource(QUrl.fromLocalFile(str(entry.file)))
            player.play()
        elif entry.kind in ('model','spine'):
            p = self.proc = QProcess(self)
            p.setWorkingDirectory(str(ROOT))
            p.readyReadStandardError.connect(lambda:p.readAllStandardError())
            p.readyReadStandardOutput.connect(lambda:self.read_frames(p))
            p.started.connect(self.request_frame)
            p.finished.connect(lambda *_:self.fail('模型渲染进程已退出，请检查模型资源。') if p is self.proc else None)
            p.errorOccurred.connect(lambda err:self.fail(p.errorString()) if p is self.proc and err==QProcess.FailedToStart else None)
            renderer = 'model_player.py' if entry.kind=='model' else 'spine_player.py'
            p.start(sys.executable,['-X','utf8',str(ROOT/renderer),str(entry.file)])
            self.tick.start(80 if entry.kind=='spine' else 50)
        elif entry.kind=='animation':
            movie = self.movie = QMovie(str(entry.file))
            movie.frameChanged.connect(lambda _:self.frame.emit(movie.currentPixmap()))
            movie.finished.connect(lambda:movie.start() if self.movie is movie else None)
            movie.error.connect(lambda _:self.fail('动图无法播放。'))
            movie.start()
        else:
            pix = QPixmap(str(entry.file))
            if pix.isNull():
                self.fail('背景文件无法读取。')
            else:
                self.frame.emit(pix)

    def request_frame(self):
        if self.proc and self.proc.state()==QProcess.Running and not self.pending and not self.parent().isMinimized():
            self.pending = True
            self.proc.write(b'frame\n')
            self.timeout.start(20000)

    def read_frames(self,p):
        if self.proc is not p:
            return
        self.buffer.extend(bytes(p.readAllStandardOutput()))
        length = SIZE*SIZE*4
        if len(self.buffer)>=length:
            data = bytes(self.buffer[:length])
            del self.buffer[:length]
            self.pending = False
            self.timeout.stop()
            self.frame.emit(QPixmap.fromImage(QImage(data,SIZE,SIZE,4*SIZE,QImage.Format_RGBA8888)))
