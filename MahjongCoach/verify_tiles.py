"""Check tile rows survive repeated live refreshes and hidden-to-visible changes."""
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from studio import Hero, TileGrid, stylesheet, ROOT
from PySide6.QtGui import QPixmap


def check():
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.setStyleSheet(stylesheet('深色'))
    box = QVBoxLayout(window)
    tiles = TileGrid()
    box.addWidget(tiles)
    window.resize(480,300)
    window.show()
    hand = ['4m','6m','6m','1p','2p','3p','3p','5p','5p','3s','9s','5z','6z']
    for width in (480,800,330,480):
        window.resize(width,300)
        app.processEvents()
        for _ in range(4):
            tiles.display([])
            tiles.hide()
            app.processEvents()
            tiles.display(hand,{t:0.2 for t in hand})
            tiles.show()
            app.processEvents()
            tiles.display(hand,{t:0.3 for t in hand})
            app.processEvents()
            assert tiles.height()>0
            assert tiles.grid.count()==len(hand)
            assert all(item.isVisible() and item.height()>0 for item in tiles.items)
            assert all(item.geometry().bottom()<tiles.height() for item in tiles.items)
    window.close()
    banner_window = QWidget()
    banner_window.setStyleSheet(stylesheet('深色'))
    layout = QVBoxLayout(banner_window)
    hero = Hero(QPixmap(str(ROOT/'雀室.webp')))
    layout.addWidget(hero)
    hero.title.setText('打九索')
    hero.copy.setText('当前有对手威胁，保留换牌余地。'*6)
    hero.alert.setText('当前第 1 名，领先末位 4,000 点。'*4)
    banner_window.show()
    for width in (450,550,800):
        banner_window.resize(width,184)
        for code in ('9s','1p','7z','0m'):
            hero.set_tile(code)
            app.processEvents()
            pix = hero.tile.pixmap().deviceIndependentSize()
            assert hero.tile.width()>=pix.width()+4
            assert hero.tile.height()>=pix.height()+4
            bottom = hero.tile.mapTo(hero,hero.tile.rect().bottomRight())
            assert hero.rect().contains(bottom)
    banner_window.close()
    print('PASS: visible tiles, repeated refresh, hidden-to-visible and responsive rows')


if __name__=='__main__':
    check()
