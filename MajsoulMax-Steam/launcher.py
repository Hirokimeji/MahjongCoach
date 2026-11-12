"""Local Steam launcher. Uses the existing Clash Verge installation."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse

import yaml

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'app' / 'MajsoulMax'
VERGE = Path(os.environ['APPDATA']) / 'io.github.clash-verge-rev.clash-verge-rev'
STATE = ROOT / 'launcher-state.json'
SCRIPT = VERGE / 'profiles' / 'Script.js'
BACKUP = ROOT / 'original-Script.js'
NODE = 'MajsoulMax-Local'
GROUP = 'MajsoulMax-Steam'
UPSTREAM = '🔰 选择节点'
GAME = Path(r'D:\SteamLibrary\steamapps\common\MahjongSoul\Jantama_MahjongSoul.exe')
RULES = [
    f'PROCESS-NAME,MajsoulMax.exe,{UPSTREAM}',
    f'AND,((PROCESS-NAME,Jantama_MahjongSoul.exe),(NETWORK,TCP)),{GROUP}',
    f'AND,((PROCESS-NAME,雀魂麻將.exe),(NETWORK,TCP)),{GROUP}',
]
HIDDEN = subprocess.CREATE_NO_WINDOW


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding='utf-8-sig')) or {}


def state_read():
    return json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}


def state_save(state):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATE)


class PipeSocket:
    def __init__(self, file):
        self.file = file

    def makefile(self, *_):
        return self.file


def api(route, method='GET', data=None):
    config = read_yaml(VERGE / 'clash-verge.yaml')
    pipe = config.get('external-controller-pipe', '')
    candidates = [pipe, pipe.replace('sidecar-release', 'production')]
    body = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else b''
    headers = (
        f'{method} {route} HTTP/1.1\r\nHost: localhost\r\n'
        f"Authorization: Bearer {config.get('secret', '')}\r\n"
        f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
    ).encode('utf-8')
    for candidate in dict.fromkeys(candidates):
        if not candidate:
            continue
        try:
            stream = open(candidate, 'r+b', buffering=0)
        except FileNotFoundError:
            continue
        with stream:
            stream.write(headers + body)
            response = http.client.HTTPResponse(PipeSocket(stream))
            response.begin()
            payload = response.read()
            if response.status >= 400:
                # Do not echo arbitrary controller responses containing configuration.
                raise RuntimeError(f'Clash API {method} {route}: HTTP {response.status}')
            return json.loads(payload) if payload else None
    raise RuntimeError('无法连接 Clash Verge，请先打开 Clash Verge，再双击启动。')


def transform(config, enabled):
    config['proxies'] = [p for p in config.get('proxies', []) if p.get('name') != NODE]
    config['proxy-groups'] = [p for p in config.get('proxy-groups', []) if p.get('name') != GROUP]
    config['rules'] = [r for r in config.get('rules', []) if r not in RULES]
    if enabled:
        config['proxies'].append({'name': NODE, 'type': 'http', 'server': '127.0.0.1', 'port': 23410})
        config['proxy-groups'].append({'name': GROUP, 'type': 'select', 'proxies': ['DIRECT', NODE]})
        config['rules'] = RULES + config['rules']
        config['find-process-mode'] = 'strict'
    return config


def reload_config(enabled, previous=None):
    # Keep existing selections when reloading the same subscription.
    selections = {name: p['now'] for name, p in api('/proxies')['proxies'].items()
                  if p.get('type') == 'Selector' and 'now' in p and name != GROUP}
    config = transform(read_yaml(VERGE / 'clash-verge.yaml'), enabled)
    if enabled and UPSTREAM not in {p.get('name') for p in config.get('proxy-groups', [])}:
        raise RuntimeError(f'当前 Clash 订阅没有 {UPSTREAM} 代理组，请切回配置时使用的订阅。')
    if previous:
        config['mode'] = previous['mode']
        config.setdefault('tun', {})['enable'] = previous['tun_enabled']
        if previous.get('find_process_mode') is None:
            config.pop('find-process-mode', None)
        else:
            config['find-process-mode'] = previous['find_process_mode']
    else:
        config['mode'] = 'rule'
        config.setdefault('tun', {})['enable'] = True
    api('/configs?force=true', 'PUT', {'payload': yaml.safe_dump(config, allow_unicode=True, sort_keys=False)})
    available = api('/proxies')['proxies']
    for name, selected in selections.items():
        if selected in available.get(name, {}).get('all', []):
            api('/proxies/' + urllib.parse.quote(name, safe=''), 'PUT', {'name': selected})
    if enabled:
        api('/proxies/' + GROUP, 'PUT', {'name': NODE})


def install_extension(state):
    current = SCRIPT.read_bytes() if SCRIPT.exists() else b'function main(config) { return config; }'
    if state.get('extension_hash'):
        if hashlib.sha256(current).hexdigest() != state['extension_hash']:
            raise RuntimeError('全局扩展脚本已被另外修改，请先使用“停止并恢复”再重新启动。')
        return
    BACKUP.write_bytes(current)
    addition = '''
// MajsoulMax Steam launcher: game process TCP only.
const __majsoulPreviousMain = main;
main = function(config, profileName) {
  config = __majsoulPreviousMain(config, profileName) || config;
  const node = 'MajsoulMax-Local', group = 'MajsoulMax-Steam';
  const rules = __RULES__;
  config.proxies = (config.proxies || []).filter(p => p.name !== node);
  config.proxies.push({name: node, type: 'http', server: '127.0.0.1', port: 23410});
  config['proxy-groups'] = (config['proxy-groups'] || []).filter(p => p.name !== group);
  config['proxy-groups'].push({name: group, type: 'select', proxies: ['DIRECT', node]});
  config.rules = rules.concat((config.rules || []).filter(r => !rules.includes(r)));
  config['find-process-mode'] = 'strict';
  return config;
};
'''.replace('__RULES__', json.dumps(RULES, ensure_ascii=False))
    content = current.decode('utf-8-sig') + addition
    SCRIPT.write_text(content, encoding='utf-8')
    state['extension_hash'] = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    state_save(state)


def port_open():
    try:
        with socket.create_connection(('127.0.0.1', 23410), timeout=0.5):
            return True
    except OSError:
        return False


def trusted_certificate(state):
    cert = Path.home() / '.mitmproxy' / 'mitmproxy-ca-cert.cer'
    pem = cert.read_text(encoding='ascii')
    der = ssl.PEM_cert_to_DER_cert(pem)
    thumb = hashlib.sha1(der).hexdigest().upper()
    already = any(hashlib.sha1(c[0]).hexdigest().upper() == thumb for c in ssl.enum_certificates('ROOT'))
    if not already:
        subprocess.run(['certutil', '-user', '-addstore', 'Root', str(cert)],
                       check=True, capture_output=True, creationflags=HIDDEN)
        state['added_certificate'] = thumb
        state_save(state)


def start(no_game=False):
    if not GAME.exists():
        raise RuntimeError('未找到已安装的 Steam 雀魂。')
    previous = api('/configs')
    state = state_read()
    if not state.get('active'):
        generated = read_yaml(VERGE / 'clash-verge.yaml')
        state['previous'] = {'mode': previous['mode'], 'tun_enabled': previous.get('tun', {}).get('enable', False),
                             'find_process_mode': generated.get('find-process-mode')}
    print('正在启动雀魂 MAX……', flush=True)
    if not port_open():
        environment = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        with (ROOT / 'max.log').open('ab') as log:
            process = subprocess.Popen([str(APP / 'MajsoulMax.exe')], cwd=APP, env=environment,
                                       stdout=log, stderr=log, creationflags=HIDDEN)
        state['pid'] = process.pid
        state_save(state)
        deadline = time.monotonic() + 100
        while not port_open():
            if process.poll() is not None:
                raise RuntimeError('雀魂 MAX 启动失败，请查看文件夹里的 max.log。')
            if time.monotonic() >= deadline:
                raise RuntimeError('雀魂 MAX 启动超时，请查看 max.log 后重试。')
            time.sleep(0.5)
    else:
        # Adopt only the official executable in this package, never an unrelated listener.
        command = "(Get-NetTCPConnection -LocalPort 23410 -State Listen | Select-Object -First 1).OwningProcess"
        result = subprocess.run(['powershell', '-NoProfile', '-Command', command],
                                capture_output=True, text=True, check=True, creationflags=HIDDEN)
        pid = int(result.stdout.strip())
        command = f'[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); (Get-Process -Id {pid}).Path'
        result = subprocess.run(['powershell', '-NoProfile', '-Command', command],
                                capture_output=True, text=True, check=True, creationflags=HIDDEN, encoding='utf-8')
        if Path(result.stdout.strip()).resolve() != (APP / 'MajsoulMax.exe').resolve():
            raise RuntimeError('23410 端口被其他程序占用，已停止配置。')
        state['pid'] = pid
        state_save(state)
    trusted_certificate(state)
    install_extension(state)
    reload_config(True)
    live = api('/configs')
    if not live.get('tun', {}).get('enable') or api('/proxies/' + GROUP)['now'] != NODE:
        raise RuntimeError('Clash 分流未生效，请查看 Clash Verge。')
    state['active'] = True
    state_save(state)
    print('本地程序、证书、Steam 进程分流均已就绪。', flush=True)
    if not no_game:
        os.startfile('steam://rungameid/1329410')
        print('已请求 Steam 启动雀魂。如提示更新，请等待 Steam 更新完成。', flush=True)
    print('结束游玩后，在启动管理窗口点击“停止并恢复”。', flush=True)


def stop(remove_certificate=False):
    state = state_read()
    if not state:
        print('当前没有需要恢复的启动配置。')
        return
    # Restore routing before stopping the proxy, preventing an unusable game route.
    reload_config(False, state.get('previous'))
    if state.get('extension_hash') and BACKUP.exists():
        if hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == state['extension_hash']:
            SCRIPT.write_bytes(BACKUP.read_bytes())
            state.pop('extension_hash', None)
        else:
            print('全局脚本另有修改，已保留；可从 original-Script.js 查看原始内容。')
    pid = state.get('pid')
    if pid:
        # Check executable path again to protect against Windows reusing an old PID.
        escaped = str(APP / 'MajsoulMax.exe').replace("'", "''")
        command = (f"$p = Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue; "
                   f"if ($p -and $p.Path -eq '{escaped}') {{ Stop-Process -Id $p.Id }}")
        subprocess.run(['powershell', '-NoProfile', '-Command', command], check=True, creationflags=HIDDEN)
    if remove_certificate and state.get('added_certificate'):
        subprocess.run(['certutil', '-user', '-delstore', 'Root', state['added_certificate']],
                       check=True, capture_output=True, creationflags=HIDDEN)
        state.pop('added_certificate', None)
    state['active'] = False
    state.pop('pid', None)
    state_save(state)
    print('已停止雀魂 MAX，并恢复 Clash 原有分流和模式。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'cleanup', 'status'])
    parser.add_argument('--no-game', action='store_true')
    args = parser.parse_args()
    # Prevent concurrent start/stop operations from corrupting the recovery state.
    import msvcrt
    with (ROOT / '.launcher.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('启动或恢复操作正在进行，请稍等。')
        if args.action == 'start':
            try:
                start(args.no_game)
            except Exception:
                try:
                    stop()
                except Exception:
                    print('自动恢复未完成，请保持 Clash Verge 开启后运行“停止并恢复”。')
                raise
        elif args.action in ('stop', 'cleanup'):
            stop(remove_certificate=args.action == 'cleanup')
        else:
            live = api('/configs')
            print(json.dumps({'max_port_ready': port_open(), 'mode': live.get('mode'),
                              'tun_enabled': live.get('tun', {}).get('enable'),
                              'active': state_read().get('active', False)}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except Exception as error:
        print(f'操作未完成：{error}', file=sys.stderr)
        sys.exit(1)
