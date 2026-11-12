from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parent / 'tiles'
root.mkdir(exist_ok=True)
names = [f'{s}{i}.png' for s in ('Man', 'Pin', 'Sou') for i in range(1, 10)]
names += [f'{s}5-Dora.png' for s in ('Man', 'Pin', 'Sou')]
names += [f'{s}.png' for s in ('Ton', 'Nan', 'Shaa', 'Pei', 'Haku', 'Hatsu', 'Chun', 'Back')]
def download(name):
    url = 'https://raw.githubusercontent.com/FluffyStuff/riichi-mahjong-tiles/master/Export/Regular/' + name
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read()
    if not data.startswith(b'\x89PNG'):
        raise ValueError('Invalid tile PNG: ' + name)
    (root / name).write_bytes(data)
with ThreadPoolExecutor(max_workers=6) as executor:
    list(executor.map(download, names))
print('Downloaded', len(names), 'CC0 tile images.')
