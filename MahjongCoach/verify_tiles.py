"""Check tile rows survive repeated live refreshes and hidden-to-visible changes."""
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from studio import TileGrid, stylesheet


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
    print('PASS: visible tiles, repeated refresh, hidden-to-visible and responsive rows')


if __name__=='__main__':
    check()
