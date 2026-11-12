"""Check actual MAX WebSocket -> protobuf -> helper -> coach using localhost only."""
import base64
import hashlib
import json
import socket
import struct
import threading
import time

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.json_format import ParseDict

import backend

pool = descriptor_pool.DescriptorPool()
pool.AddSerializedFile(descriptor_pb2.DESCRIPTOR.serialized_pb)
fds = descriptor_pb2.FileDescriptorSet()
fds.ParseFromString((backend.max_launcher.APP/'proto/liqi.desc').read_bytes())
pending = list(fds.file)
while pending:
    count = len(pending)
    for fd in pending[:]:
        try:
            pool.Add(fd)
        except Exception:
            continue
        pending.remove(fd)
    if len(pending) == count:
        raise RuntimeError('Unresolved descriptor dependencies')


def message(name):
    return message_factory.GetMessageClass(pool.FindMessageTypeByName('lq.' + name))()


def action(name, data):
    body = message(name)
    ParseDict(data, body)
    blob = bytearray(body.SerializeToString())
    keys = [0x84,0x5e,0x4e,0x42,0x39,0xa2,0x1f,0x60,0x1c]
    size = len(blob)
    for i in range(size):
        blob[i] ^= ((23 ^ size) + 5*i + keys[i % len(keys)]) & 255
    prototype = message('ActionPrototype')
    prototype.name, prototype.data = name, bytes(blob)
    wrapper = message('Wrapper')
    wrapper.name, wrapper.data = '.lq.ActionPrototype', prototype.SerializeToString()
    return b'\x01' + wrapper.SerializeToString()


def wait_for(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = backend.local_request('/state')
        if predicate(result):
            return result
        time.sleep(0.05)
    raise AssertionError(('MAX capture did not produce expected coach state', result))


backend.local_request('/events', {'account_id':987654321})
backend.local_request('/events', {'seat_list':[987654321,0,0,0],'is_game_start':False,
                                 'game_config':{'category':1,'mode':{'mode':1}}})
listener = socket.socket()
listener.bind(('127.0.0.1', 0))
listener.listen(1)
port = listener.getsockname()[1]
release = threading.Event()
packets = [action('ActionNewRound', {
    'chang':0,'ju':1,'ben':0,'tiles':['2m','4m','5m','2p','3p','4p','5p','6p','7p','4s','5s','6s','7s'],
    'doras':['9m'],'scores':[25000]*4,'left_tile_count':69,'sha256':'a'*64,
}), action('ActionDealTile', {
    'seat':0,'tile':'7z','left_tile_count':65,'operation':{'seat':0,'operation_list':[{'type':1}]},
})]


def server():
    connection, _ = listener.accept()
    with connection:
        headers = b''
        while b'\r\n\r\n' not in headers:
            headers += connection.recv(4096)
        key = next(line.split(b':', 1)[1].strip() for line in headers.split(b'\r\n') if line.lower().startswith(b'sec-websocket-key:'))
        accept = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
        connection.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
        for payload in packets:
            length = len(payload)
            frame = b'\x82' + (bytes([length]) if length<126 else b'\x7e'+struct.pack('!H',length)) + payload
            connection.sendall(frame)
            time.sleep(0.6)
        release.wait(12)


thread = threading.Thread(target=server, daemon=True)
thread.start()
client = socket.create_connection(('127.0.0.1',23410), timeout=5)
try:
    key = base64.b64encode(b'coach-local-test')
    request = f'GET http://127.0.0.1:{port}/coach-test HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: '.encode() + key + b'\r\n\r\n'
    client.sendall(request)
    response = client.recv(8192)
    assert b'101 Switching Protocols' in response, response[:100]
    result = wait_for(lambda s:s.get('kind')=='discard' and s.get('candidates',[{}])[0].get('tile')=='7z')
    assert result['candidates'][0]['ukeire']==20
    print('PASS: real MAX proxy captured local WebSocket, decoded current protobuf and forwarded helper data to the beginner coach.')
finally:
    release.set()
    client.close()
    listener.close()
    thread.join(timeout=2)
