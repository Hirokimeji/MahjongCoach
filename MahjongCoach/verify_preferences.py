"""Verify close/reopen persistence without changing the user's preferences."""
from pathlib import Path
import runpy
import tempfile
from unittest.mock import patch
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication


def check():
    app = QApplication.instance() or QApplication([])
    Coach = runpy.run_path(str(Path(__file__).parent/'coach.pyw'),run_name='qa')['Coach']
    Coach.choose_background = lambda *args,**kwargs:None
    Coach.needs_restore = lambda self:False
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        ini = str(Path(folder)/'appearance.ini')
        factory = lambda:QSettings(ini,QSettings.IniFormat)
        with patch.dict(Coach.__init__.__globals__,appearance_settings=factory):
            first = Coach()
            first.timer.stop()
            first.show()
            first.resize(1100,760)
            first.toggle_size()
            first.resize(520,640)
            first.move(40,50)
            first.set_theme('粉色')
            first.switch_mode('avoid_last')
            first.all_tiles.setChecked(True)
            first.set_pin(True)
            app.processEvents()
            first.close()
            app.processEvents()
            position = first.pos()
            second = Coach()
            second.timer.stop()
            second.show()
            app.processEvents()
            assert second.width()==520 and second.height()==640
            assert second.pos()==position
            assert second.theme=='粉色' and second.strategy=='avoid_last'
            assert second.pin.isChecked() and second.windowFlags() & Qt.WindowStaysOnTopHint
            assert second.all_tiles.isChecked()
            assert second.normal_size.width()==1100
            second.close()
            app.processEvents()
            third = Coach()
            third.timer.stop()
            third.showMaximized()
            app.processEvents()
            third.close()
            app.processEvents()
            fourth = Coach()
            fourth.timer.stop()
            fourth.show()
            app.processEvents()
            assert fourth.isMaximized()
            fourth.close()
            app.processEvents()
    print('PASS: reopened small window, saved large size, position, theme, pin, strategy and tile scope')


if __name__=='__main__':
    check()
