"""Install stable Windows releases into the existing portable MAX directory."""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import tempfile
import zipfile

REPO = 'Avenshy/MajsoulMax'
TAG = re.compile(r'v(\d{4})\.(\d{1,2})\.(\d{1,2})(?:\.(\d+))?')
EXE = 'MajsoulMax.exe'
MARKER = '.coach-release'


def version(tag):
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError('无法识别 MAX 正式版版本号：' + tag)
    return tuple(int(n or 0) for n in match.groups())


def fetch(url, size, output=None):
    # System curl uses the Windows certificate store and follows GitHub's
    # HTTPS asset redirect without changing the user's network settings.
    seconds = 180 if output else 12
    args = [str(Path(os.environ['SystemRoot'])/'System32/curl.exe'), '--disable',
            '--fail', '--silent', '--show-error', '--location', '--proto', '=https',
            '--proto-redir', '=https', '--connect-timeout', '8', '--max-time', str(seconds),
            '--max-filesize', str(size), '--user-agent', 'MahjongCoach-Updater']
    if output:
        args.extend(['--output', str(output)])
    result = subprocess.run([*args,url], capture_output=True, timeout=seconds+5,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise OSError(result.stderr.decode(errors='replace').strip() or '下载失败')
    return result.stdout


def installed(root, live):
    marker = live / MARKER
    if marker.is_file():
        tag = marker.read_text(encoding='ascii').strip()
        version(tag)
        return tag
    with (live / EXE).open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').digest()
    for package in sorted(root.glob('MajsoulMax_v*.zip'), reverse=True):
        tag = package.stem.removeprefix('MajsoulMax_')
        if TAG.fullmatch(tag):
            with zipfile.ZipFile(package) as archive, archive.open('MajsoulMax/'+EXE) as stream:
                if hashlib.file_digest(stream, 'sha256').digest() == digest:
                    return tag
    raise ValueError('无法确认本机 MAX 的版本，请保留原发行压缩包。')


def download(asset, tag, output):
    name = f'MajsoulMax_{tag}.zip'
    url = f'https://github.com/{REPO}/releases/download/{tag}/{name}'
    checksum = asset.get('digest') or ''
    if asset.get('browser_download_url') != url or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', checksum):
        raise ValueError('发行包缺少可验证的官方地址或 SHA-256。')
    size = asset['size']
    if not 0 < size <= 512 * 1024**2:
        raise ValueError('发行包大小异常。')
    fetch(url, size, output)
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if output.stat().st_size != size or digest != checksum[7:].lower():
        raise ValueError('发行包校验失败。')


def unpack(package, stage):
    with zipfile.ZipFile(package) as archive:
        if sum(info.file_size for info in archive.infolist()) > 2 * 1024**3:
            raise ValueError('解压后的发行包过大。')
        for info in archive.infolist():
            parts = info.filename.rstrip('/').split('/')
            if parts[0] != 'MajsoulMax' or any(
                not part or part.endswith(('.', ' ')) or re.search(r'[\\:<>|"?*\x00-\x1f]', part)
                or PureWindowsPath(part).is_reserved() for part in parts):
                raise ValueError('发行包目录结构异常。')
            target = stage.joinpath(*parts[1:])
            if info.is_dir():
                target.mkdir(exist_ok=True, parents=True)
            else:
                target.parent.mkdir(exist_ok=True, parents=True)
                with archive.open(info) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
    if not (stage/EXE).is_file() or not (stage/'config').is_dir():
        raise ValueError('发行包缺少主程序或配置目录。')


def migrate(root, live, stage, previous):
    # Keep local resources only when the publisher has left the corresponding
    # base file unchanged. Preserve user settings even if the layout changes.
    base = root/f'MajsoulMax_{previous}.zip'
    if base.is_file():
        with zipfile.ZipFile(base) as old:
            for item in old.infolist():
                if item.is_dir() or not item.filename.startswith(('MajsoulMax/proto/', 'MajsoulMax/config/')):
                    continue
                relative = Path(item.filename).relative_to('MajsoulMax')
                if relative.is_absolute() or '..' in relative.parts:
                    continue
                src, dst = live/relative, stage/relative
                if src.is_file() and dst.is_file() and dst.read_bytes() == old.read(item):
                    shutil.copy2(src, dst)
    for settings in (live/'config').glob('settings*.yaml'):
        shutil.copy2(settings, stage/'config'/settings.name)
    # Let MAX detect its supplied data version if the release changed it.
    desc = Path('proto/liqi.desc')
    if (stage/desc).is_file() and (live/desc).is_file() and (stage/desc).read_bytes() != (live/desc).read_bytes():
        import yaml
        settings = stage/'config/settings.yaml'
        if settings.is_file():
            data = yaml.safe_load(settings.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('liqi'), dict):
                data['liqi'].pop('liqi_version', None)
                settings.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')


def update(root, busy, report=print):
    live = root/'app/MajsoulMax'
    backup = live.with_name('MajsoulMax.previous')
    if busy():
        return 'MAX 正在使用，已推迟更新。'
    if not live.exists() and backup.is_dir():
        backup.rename(live)
    local = installed(root, live)
    release = json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases/latest', 2*1024**2))
    tag = release['tag_name']
    if release.get('prerelease') or release.get('draft') or version(tag) <= version(local):
        return f'MAX {local} · 已是最新正式版'
    name = f'MajsoulMax_{tag}.zip'
    asset = next((a for a in release['assets'] if a['name'] == name), None)
    if not asset:
        raise ValueError('新版本尚无对应的 Windows 发行包。')
    report(f'正在下载 MAX {tag}…')
    with tempfile.TemporaryDirectory(prefix='.max-update-', dir=live.parent) as tmp:
        stage = Path(tmp)/'next'
        package = Path(tmp)/name
        download(asset, tag, package)
        unpack(package, stage)
        if busy():
            return 'MAX 正在使用，已推迟更新。'
        migrate(root, live, stage, local)
        (stage/MARKER).write_text(tag, encoding='ascii')
        package.replace(root/name)
        if backup.exists():
            backup.rename(Path(tmp)/'older')
        live.rename(backup)
        try:
            stage.rename(live)
        except OSError:
            backup.rename(live)
            raise
    return f'MAX 已更新至 {tag} · 已保留上一版和个人配置'
