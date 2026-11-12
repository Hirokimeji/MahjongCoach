"""Connection settings for a portable installation."""
import json
from pathlib import Path
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout)
import backend


def edit_connection(parent=None):
    launcher = backend.max_launcher
    dialog = QDialog(parent)
    dialog.setWindowTitle('连接设置')
    dialog.resize(620,260)
    box = QVBoxLayout(dialog)
    text = QLabel('先在 Steam 安装并更新雀魂，再打开 Clash Verge Rev。\n选择游戏程序、Clash 配置目录和网络出口。')
    text.setWordWrap(True)
    box.addWidget(text)
    form = QFormLayout()
    box.addLayout(form)
    game = QLineEdit(str(launcher.GAME) if launcher.SETTINGS.exists() else '')
    verge = QLineEdit(str(launcher.VERGE))
    for title, field, folder in [('雀魂程序',game,False),('Clash 配置目录',verge,True)]:
        row = QHBoxLayout()
        row.addWidget(field)
        button = QPushButton('选择')
        def browse(checked=False, target=field, directory=folder):
            result = (QFileDialog.getExistingDirectory(dialog,'选择 Clash 配置目录',target.text()) if directory
                      else QFileDialog.getOpenFileName(dialog,'选择雀魂程序',target.text(),'程序 (*.exe)')[0])
            if result:
                target.setText(result)
        button.clicked.connect(browse)
        row.addWidget(button)
        form.addRow(title,row)
    upstream = QComboBox()
    upstream.setEditable(True)
    upstream.addItem('DIRECT')
    def refresh():
        try:
            config = launcher.read_yaml(Path(verge.text())/'clash-verge.yaml')
            previous = upstream.currentText()
            upstream.clear()
            upstream.addItems(list(dict.fromkeys(['DIRECT']+[p['name'] for p in config.get('proxy-groups',[])])))
            upstream.setCurrentText(previous)
        except (OSError,ValueError,KeyError) as error:
            QMessageBox.warning(dialog,'读取配置失败',str(error))
    refresh_button = QPushButton('读取代理组')
    refresh_button.clicked.connect(refresh)
    row = QHBoxLayout()
    row.addWidget(upstream,1)
    row.addWidget(refresh_button)
    form.addRow('MAX 网络出口',row)
    hint = QLabel('DIRECT 为直接连接。需要代理时，选择能访问雀魂的代理组。\n首次设置可取消并先试用示例手牌。')
    hint.setWordWrap(True)
    box.addWidget(hint)
    buttons = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
    box.addWidget(buttons)
    buttons.rejected.connect(dialog.reject)
    def save():
        path = Path(game.text().strip())
        directory = Path(verge.text().strip())
        name = upstream.currentText().strip()
        try:
            if not path.is_file() or path.name not in ('Jantama_MahjongSoul.exe','雀魂麻將.exe'):
                raise ValueError('在 Steam 右键雀魂 → 管理 → 浏览本地文件，选择 Jantama_MahjongSoul.exe。')
            config = launcher.read_yaml(directory/'clash-verge.yaml')
            if not config.get('external-controller-pipe'):
                raise ValueError('请打开 Clash Verge Rev 并启用配置，确保使用 Windows 命名管道控制接口。')
            names = {'DIRECT',*[p['name'] for p in config.get('proxy-groups',[])]}
            if name not in names or any(c in name for c in ',\r\n'):
                raise ValueError('请读取代理组后选择有效的网络出口。')
            backend.atomic_text(launcher.SETTINGS,json.dumps(dict(game=str(path.resolve()),
                verge=str(directory.resolve()),upstream=name),ensure_ascii=False,indent=2))
            launcher.configure()
            dialog.accept()
        except (OSError,ValueError) as error:
            QMessageBox.warning(dialog,'设置未保存',str(error))
    buttons.accepted.connect(save)
    return dialog.exec() == QDialog.Accepted
