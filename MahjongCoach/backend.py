"""Local-only coach relay and start/restore lifecycle around the existing launcher."""
from __future__ import annotations

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import msvcrt
import os
from pathlib import Path
import queue
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
import tempfile
import urllib.request

import yaml
from table_context import TableContext

ROOT = Path(__file__).resolve().parent
MAX_ROOT = ROOT.parent / 'MajsoulMax-Steam'
sys.path.insert(0, str(MAX_ROOT))
import launcher as max_launcher

ENGINE = ROOT / 'engine' / 'mahjong-coach-engine.exe'
SESSION = ROOT / 'session.json'
HELPER_SETTINGS = max_launcher.APP / 'config' / 'settings.helper.yaml'
MAX_SETTINGS = max_launcher.APP / 'config' / 'settings.yaml'
SKIN_SETTINGS = max_launcher.APP / 'config' / 'settings.mod.yaml'
SKIN_BACKUP = ROOT / '角色皮肤.json'
LOCAL = 'http://127.0.0.1:12122'
EVENT_URL = LOCAL + '/events'
HIDDEN = subprocess.CREATE_NO_WINDOW
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def read_session():
    return json.loads(SESSION.read_text(encoding='utf-8')) if SESSION.exists() else {}


def save_session(state):
    temp = SESSION.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(SESSION)


def atomic_text(path, content):
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False,mode='w',encoding='utf-8') as f:
        temp = Path(f.name)
        try:
            f.write(content)
        except Exception:
            f.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def skin_choices(config):
    skins = {int(k):int(v) for k,v in config['characters'].items()}
    selected = int(config['character'])
    if not skins or selected not in skins or any(k<=0 or v<=0 for k,v in skins.items()):
        raise ValueError('皮肤设置尚未完整，请在游戏里选好角色和皮肤后再保存。')
    return selected, skins


def save_skin_choices():
    selected,skins = skin_choices(max_launcher.read_yaml(SKIN_SETTINGS)['config'])
    atomic_text(SKIN_BACKUP,json.dumps(dict(character=selected,characters=skins),indent=2))
    return len(skins)


def restore_skin_choices():
    if not SKIN_BACKUP.exists():
        return
    selected,skins = skin_choices(json.loads(SKIN_BACKUP.read_text(encoding='utf-8')))
    data = max_launcher.read_yaml(SKIN_SETTINGS)
    config = data['config']
    current = config.setdefault('characters',{})
    if config.get('character')==selected and all(current.get(k)==v for k,v in skins.items()):
        return
    current.update(skins)
    config['character'] = selected
    atomic_text(SKIN_SETTINGS,yaml.safe_dump(data,allow_unicode=True,sort_keys=False))


def local_request(path, data=None, timeout=2):
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(LOCAL + path, data=body, headers={'Content-Type': 'application/json'})
    with OPENER.open(request, timeout=timeout) as response:
        return json.loads(response.read())


def alive():
    try:
        return local_request('/health', timeout=0.6).get('application') == 'MahjongCoach'
    except (OSError, ValueError):
        return False


def port_in_use(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.3):
            return True
    except OSError:
        return False


class Relay:
    def __init__(self, token):
        self.token = token
        self.events = queue.Queue(maxsize=128)
        self.lock = threading.Lock()
        self.sequence = 0
        self.table = TableContext()
        self.latest = {'kind': 'connected', 'message': '已连接，等待新的一局。', 'time': int(time.time() * 1000)}
        self.stopping = threading.Event()
        self.engine = subprocess.Popen([str(ENGINE), '-majsoul', '-port', '12121'], cwd=ENGINE.parent,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       encoding='utf-8', errors='replace', creationflags=HIDDEN)
        self.engine_opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            # The legacy engine uses its own expired test cert. This exception
            # is restricted to the loopback-only engine, never game connections.
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
        threading.Thread(target=self.read_engine, daemon=True).start()
        threading.Thread(target=self.forward, daemon=True).start()

    def snapshot(self):
        with self.lock:
            result = dict(self.latest)
            result.update(self.table.values())
        result['service_running'] = not self.stopping.is_set()
        result['engine_running'] = self.engine.poll() is None
        if not result['engine_running']:
            result.update(kind='error', message='分析引擎已停止，请停止后重新启动。')
        elif (result.get('kind') == 'discard' or (result.get('legal_operations') or {}).get('operation_list')) and time.time()*1000-result.get('time',0)>30_000:
            result.update(kind='error', message='已超过30秒没有新动作，已隐藏旧建议。等待新数据；若持续无响应，请停止后重开。')
        return result

    def error(self, message):
        with self.lock:
            self.latest = {'kind': 'error', 'message': message, 'time': int(time.time() * 1000)}

    def receive(self, data):
        with self.lock:
            self.table.update(data)
        # The helper repeats the riichi payment attached to a draw or call.
        # This receipt does not advance play or dismiss that action's buttons.
        if {'seat', 'score', 'liqibang'} <= data.keys() <= {
            'seat', 'score', 'liqibang', 'failed', 'liqi_type_beishuizhizhan', 'xia_ke_shang'
        }:
            return
        # Unknown future game actions also invalidate an old recommendation.
        actionable = not ('friends' in data or 'record_list' in data)
        with self.lock:
            if actionable:
                self.sequence += 1
                self.latest = {'kind': 'processing', 'time': int(time.time() * 1000)}
            data['__coach_seq'] = self.sequence if actionable else -1
        try:
            self.events.put_nowait(data)
        except queue.Full:
            self.error('分析队列过长，已隐藏旧提示。请停止并从新的一局重新开始。')

    def read_engine(self):
        with (ROOT / 'engine.log').open('a', encoding='utf-8') as log:
            for line in self.engine.stdout:
                if 'COACH_JSON:' in line:
                    try:
                        result = json.loads(line.split('COACH_JSON:', 1)[1])
                    except ValueError:
                        continue
                    with self.lock:
                        # A recommendation for an older event must never replace
                        # the processing/wait state for a newer game event.
                        if result.get('source_sequence') == self.sequence:
                            self.latest = result
                else:
                    log.write(line)
                    log.flush()

    def forward(self):
        while not self.stopping.is_set():
            try:
                data = self.events.get(timeout=0.3)
            except queue.Empty:
                continue
            try:
                request = urllib.request.Request('https://127.0.0.1:12121/majsoul',
                    data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
                with self.engine_opener.open(request, timeout=3) as response:
                    response.read()
            except OSError:
                self.error('暂时无法连接分析引擎，已隐藏旧提示。请停止后重新启动。')

    def close(self):
        self.stopping.set()
        if self.engine.poll() is not None:
            return
        self.engine.terminate()
        try:
            self.engine.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.engine.kill()
            self.engine.wait(timeout=3)


def serve():
    state = read_session()
    relay = Relay(state['token'])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/health':
                self.respond(200, {'application': 'MahjongCoach', 'engine_running': relay.engine.poll() is None})
            elif self.path == '/state':
                self.respond(200, relay.snapshot())
            else:
                self.respond(404, {})

        def do_POST(self):
            if self.headers.get('Origin') or self.headers.get_content_type() != 'application/json':
                self.respond(403, {})
                return
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 2_000_000:
                self.respond(413, {})
                return
            try:
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('object required')
            except ValueError:
                self.respond(400, {})
                return
            if self.path == '/events':
                relay.receive(data)
                self.respond(200, {'received': True})
            elif self.path == '/shutdown' and secrets.compare_digest(str(data.get('token', '')), relay.token):
                self.respond(200, {'stopping': True})
                threading.Thread(target=server.shutdown, daemon=True).start()
            else:
                self.respond(403, {})

    try:
        server = ThreadingHTTPServer(('127.0.0.1', 12122), Handler)
        server.serve_forever(poll_interval=0.2)
    finally:
        relay.close()
        if 'server' in locals():
            server.server_close()


def restore_helper(state):
    if 'helper_enabled_before' not in state:
        return
    config = max_launcher.read_yaml(MAX_SETTINGS)
    plugins = config.setdefault('plugin_enable', {})
    plugins['helper'] = state['helper_enabled_before']
    if 'appearance_plugins_before' in state:
        previous = state['appearance_plugins_before']
        for name in ('mod', 'replace'):
            if name in previous:
                plugins[name] = previous[name]
            else:
                plugins.pop(name, None)
    atomic_text(MAX_SETTINGS, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    if HELPER_SETTINGS.exists():
        current = max_launcher.read_yaml(HELPER_SETTINGS)
        if current.get('config', {}).get('api_url') == EVENT_URL:
            if state.get('helper_file_before') is not None:
                HELPER_SETTINGS.write_bytes(base64.b64decode(state['helper_file_before']))
            else:
                HELPER_SETTINGS.unlink()
    state.pop('helper_enabled_before', None)
    state.pop('helper_file_before', None)
    state.pop('appearance_plugins_before', None)
    save_session(state)


def stop():
    state = read_session()
    max_state = max_launcher.state_read()
    if max_state.get('active') or max_state.get('pid') or max_state.get('extension_hash'):
        print('正在恢复雀魂分流……', flush=True)
        max_launcher.stop()
    restore_helper(state)
    if alive():
        local_request('/shutdown', {'token': state.get('token', '')})
        deadline = time.monotonic() + 10
        while alive() and time.monotonic() < deadline:
            time.sleep(0.2)
        if alive():
            raise RuntimeError('分析服务仍在退出中，请稍后再次停止。')
    state.update(active=False)
    save_session(state)
    print('新手提示已停止，分流与助手配置已恢复。', flush=True)


def start(no_game=False, coach_only=False):
    state = read_session()
    if state.get('active') and alive() and max_launcher.port_open():
        print('新手教练已在运行。', flush=True)
        if not no_game:
            os.startfile('steam://rungameid/1329410')
        return
    # Verify Clash before changing settings or spawning any local service.
    max_launcher.api('/configs')
    if max_launcher.port_open():
        raise RuntimeError('雀魂 MAX 已单独运行，请先在原启动窗口停止，再启动新手教练。')
    if not ENGINE.exists():
        raise RuntimeError('分析引擎文件缺失。')
    if port_in_use(12121) or port_in_use(12122):
        raise RuntimeError('12121 或 12122 端口已被使用，请先关闭其他麻将助手。')
    if 'helper_enabled_before' in state:
        raise RuntimeError('上次启动还需要恢复，请先点击「停止并恢复」。')
    if not coach_only:
        restore_skin_choices()
    config = max_launcher.read_yaml(MAX_SETTINGS)
    plugins = config.setdefault('plugin_enable', {})
    state['helper_enabled_before'] = plugins.get('helper', False)
    state['helper_file_before'] = base64.b64encode(HELPER_SETTINGS.read_bytes()).decode() if HELPER_SETTINGS.exists() else None
    if coach_only:
        state['appearance_plugins_before'] = {k:plugins[k] for k in ('mod','replace') if k in plugins}
        plugins.update(mod=False, replace=False)
    state['token'] = secrets.token_hex(24)
    state['active'] = False
    save_session(state)
    try:
        print('正在启动本地牌效引擎……', flush=True)
        with (ROOT / 'service.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__)), 'serve'],
                                       cwd=ROOT, stdout=log, stderr=log, creationflags=HIDDEN)
        deadline = time.monotonic() + 18
        while not alive():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('本地提示服务启动失败，请查看 service.log。')
            time.sleep(0.2)
        deadline = time.monotonic() + 10
        while not port_in_use(12121):
            if time.monotonic() > deadline:
                raise RuntimeError('牌效引擎启动失败，请查看 engine.log。')
            time.sleep(0.2)
        if not local_request('/health').get('engine_running'):
            raise RuntimeError('牌效引擎启动后退出。')
        plugins['helper'] = True
        atomic_text(MAX_SETTINGS, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
        atomic_text(HELPER_SETTINGS, yaml.safe_dump({'config': {'api_url': EVENT_URL}}))
        max_launcher.start(no_game=no_game)
        state['active'] = True
        save_session(state)
        print('新手实时提示已就绪。请登录后从新的一局开始，首次建议人机练习。', flush=True)
    except Exception:
        try:
            stop()
        except Exception:
            print('自动恢复未完成，请保持 Clash 开启后在窗口点击“停止并恢复”。', flush=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['serve', 'start', 'stop', 'status', 'update'])
    parser.add_argument('--no-game', action='store_true')
    parser.add_argument('--coach-only', action='store_true')
    args = parser.parse_args()
    if args.action == 'serve':
        serve()
        return
    with (ROOT / '.operation.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('启动或恢复正在进行，请稍候。')
        if args.action == 'start':
            start(args.no_game, args.coach_only)
        elif args.action == 'stop':
            stop()
        elif args.action == 'update':
            from max_updates import update
            def busy():
                local, game = read_session(), max_launcher.state_read()
                return (local.get('active') or 'helper_enabled_before' in local or
                        game.get('active') or game.get('pid') or game.get('extension_hash') or max_launcher.port_open())
            with (MAX_ROOT/'.launcher.lock').open('a+b') as launcher_lock:
                launcher_lock.seek(0)
                msvcrt.locking(launcher_lock.fileno(), msvcrt.LK_NBLCK, 1)
                print(update(MAX_ROOT, busy, lambda msg: print(msg, flush=True)), flush=True)
        else:
            print(json.dumps({'active': read_session().get('active', False), 'service_running': alive()}, ensure_ascii=False))


if __name__ == '__main__':
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except Exception as error:
        print(f'操作未完成：{error}', file=sys.stderr)
        sys.exit(1)
