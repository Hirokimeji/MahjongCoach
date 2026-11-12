"""Desktop entry point with a persistent diagnostic log for startup failures."""
import ctypes
from pathlib import Path
import runpy
import sys
import traceback

root = Path(__file__).resolve().parent
with (root/'startup.log').open('a',encoding='utf-8',buffering=1) as log:
    sys.stdout = sys.stderr = log
    try:
        runpy.run_path(str(root/'coach.pyw'),run_name='__main__')
    except Exception:
        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(None,
            '启动失败。请查看 MahjongCoach 文件夹中的 startup.log。','雀魂新手教练',0x10)
