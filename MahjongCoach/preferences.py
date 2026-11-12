"""Persist UI preferences independently of the extracted release directory."""
import os
from pathlib import Path
from PySide6.QtCore import QSettings


def appearance_settings():
    root = Path(__file__).resolve().parent
    folder = Path(os.environ.get('LOCALAPPDATA',str(root)))/'MahjongCoach'
    folder.mkdir(parents=True,exist_ok=True)
    path = folder/'appearance.ini'
    settings = QSettings(str(path),QSettings.IniFormat)
    legacy = root/'外观.ini'
    if not path.exists() and legacy.is_file():
        previous = QSettings(str(legacy),QSettings.IniFormat)
        for key in previous.allKeys():
            settings.setValue(key,previous.value(key))
        settings.sync()
    return settings
