"""Build a portable Windows x64 release from a prepared Python environment."""
import argparse
import hashlib
import importlib.metadata
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent


def copytree(src, dst):
    shutil.copytree(src,dst,dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets',type=Path,required=True,help='Prepared engine and Live2D runtime directory')
    parser.add_argument('--max-zip',type=Path,required=True)
    parser.add_argument('--vendor',type=Path,required=True)
    parser.add_argument('--max-source',type=Path,required=True)
    args = parser.parse_args()
    dest = ROOT/'dist/MahjongCoach-v0.2.3-win-x64'
    if dest.exists():
        raise SystemExit('Output already exists. Use a fresh build directory.')
    app = dest/'MahjongCoach'
    app.mkdir(parents=True)
    for file in (ROOT/'MahjongCoach').iterdir():
        if file.is_file() and file.suffix in ('.py','.pyw','.webp','.png','.json','.md','.txt'):
            shutil.copy2(file,app/file.name)
    copytree(ROOT/'MahjongCoach/tiles',app/'tiles')
    (app/'engine').mkdir()
    shutil.copy2(args.assets/'engine/mahjong-coach-engine.exe',app/'engine/mahjong-coach-engine.exe')
    copytree(args.assets/'model-runtime',app/'model-runtime')
    maxroot = dest/'MajsoulMax-Steam'
    maxroot.mkdir()
    shutil.copy2(ROOT/'MajsoulMax-Steam/launcher.py',maxroot/'launcher.py')
    shutil.copy2(args.max_zip,maxroot/args.max_zip.name)
    (dest/'sources').mkdir()
    shutil.copy2(args.max_source,dest/'sources'/args.max_source.name)
    with zipfile.ZipFile(args.max_source) as source:
        license_name = next(n for n in source.namelist() if n.endswith('/LICENSE'))
        (maxroot/'LICENSE-MajsoulMax.txt').write_bytes(source.read(license_name))
    with zipfile.ZipFile(args.max_zip) as archive:
        archive.extractall(maxroot/'app')
    config = maxroot/'app/MajsoulMax/config/settings.yaml'
    config.write_text('plugin_enable:\n  mod: false\n  helper: false\n  replace: false\nliqi:\n  auto_update: true\n  github_token: ""\n',encoding='utf-8')
    runtime = dest/'runtime'
    runtime.mkdir()
    prefix = Path(sys.base_prefix)
    for name in ('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):
        shutil.copy2(prefix/name,runtime/name)
    copytree(prefix/'DLLs',runtime/'DLLs')
    with zipfile.ZipFile(runtime/'python312.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for file in (prefix/'Lib').rglob('*.py'):
            relative = file.relative_to(prefix/'Lib')
            if any(p in ('site-packages','__pycache__','test','tests','idlelib','tkinter','ensurepip','venv') for p in relative.parts):
                continue
            archive.write(file,relative.as_posix())
    (runtime/'python312._pth').write_text('python312.zip\nDLLs\nLib/site-packages\n../MahjongCoach\n../MajsoulMax-Steam\nimport site\n',encoding='ascii')
    site = args.vendor.resolve()
    target = runtime/'Lib/site-packages'
    for name in ('PySide6','shiboken6','yaml','PIL','numpy','numpy.libs','pillow.libs'):
        if (site/name).is_dir():
            copytree(site/name,target/name)
    for dist in ('PySide6','PySide6_Addons','PySide6_Essentials','shiboken6','PyYAML','Pillow','numpy'):
        metadata = next(d for d in importlib.metadata.distributions(path=[str(site)])
                        if d.metadata['Name'].lower().replace('_','-') == dist.lower().replace('_','-'))
        copytree(Path(metadata._path),target/Path(metadata._path).name)
    shutil.copy2(ROOT/'README.md',dest/'README.md')
    shutil.copy2(ROOT/'README.md',app/'使用说明.md')
    shutil.copy2(ROOT/'THIRD_PARTY.md',dest/'THIRD_PARTY.md')
    copytree(ROOT/'LICENSES',dest/'LICENSES')
    shutil.copy2(ROOT/'Clash-直连示例.yaml',dest/'Clash-直连示例.yaml')
    compiler = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64',
                    '/reference:System.Windows.Forms.dll','/out:'+str(dest/'雀魂新手教练.exe'),
                    str(ROOT/'Launcher.cs')],check=True)
    print(dest,flush=True)


if __name__ == '__main__':
    main()
