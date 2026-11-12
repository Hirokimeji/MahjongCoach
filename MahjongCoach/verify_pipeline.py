"""Synthetic local event checks. Never joins a game or sends game actions."""
import json
from pathlib import Path
import subprocess
import time

import backend
from presenter import present

ROOT = Path(__file__).resolve().parent
account_file = ROOT/'engine/config.json'
previous = account_file.read_bytes() if account_file.exists() else None


def send(event):
    backend.local_request('/events', event)


def wait_for(predicate, label):
    deadline = time.monotonic() + 10
    last = {}
    while time.monotonic() < deadline:
        last = backend.local_request('/state')
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError((label, last))


hand = ['2m','4m','5m','2p','3p','4p','5p','6p','7p','4s','5s','6s','7s']
new_round = dict(chang=0, ju=1, ben=0, tiles=hand, doras=['9m'], md5='0'*32,
                 scores=[25000]*4, liqibang=0, left_tile_count=69)
draw = dict(seat=0,tile='7z',left_tile_count=65,operation={'seat':0,'operation_list':[{'type':1}]})
discard = dict(seat=0,tile='7z',is_liqi=False,is_wliqi=False,moqie=True)

try:
    send({'account_id':987654321})
    send({'seat_list':[987654321,0,0,0],'is_game_start':False,
          'game_config':{'category':1,'mode':{'mode':1}}})
    send(new_round)
    wait_for(lambda s:len(s.get('hand',[]))==13,'13-tile round init')
    send(draw)
    snapshot = wait_for(lambda s:s.get('kind')=='discard','self draw')
    assert snapshot['self_seat']==0
    assert len(snapshot['hand'])==14
    assert snapshot['candidates'][0]['tile']=='7z'
    assert snapshot['candidates'][0]['ukeire']==20
    view = present(snapshot)
    assert view['tile']=='7z' and '红中' in view['title']
    assert '一次有效进张' in view['reason']
    assert len(view['waits'])==6
    send(discard)
    wait_for(lambda s:s.get('kind')=='waiting' and len(s.get('hand',[]))==13,'own discard clears stale suggestion')
    send(dict(seat=1,tile='1p',is_liqi=True,is_wliqi=False,moqie=False))
    wait_for(lambda s:bool(s.get('riichi_opponents')),'opponent riichi tracked')
    send(dict(draw,tile='9s'))
    threatened = wait_for(lambda s:s.get('kind')=='discard','threatened draw')
    assert threatened.get('defence') and 'risk' in threatened['candidates'][0]
    send(dict(seat=0,tile='9s',is_liqi=True,is_wliqi=False,moqie=True))
    wait_for(lambda s:s.get('kind')=='riichi_locked','own riichi stops discard advice')
    send({'liujumanguan':False,'scores':[]})
    wait_for(lambda s:s.get('kind')=='round_end','round end clears recommendation')
    # A delayed result for the draw must never survive the following discard.
    send(new_round); send(draw); send(discard)
    wait_for(lambda s:s.get('kind')=='waiting' and len(s.get('hand',[]))==13,'burst event ordering')
    time.sleep(0.3)
    assert backend.local_request('/state')['kind']=='waiting'
    result = subprocess.run([str(backend.ENGINE),'240m','234567p','4567s','7z'],cwd=backend.ENGINE.parent,
                            capture_output=True,text=True,encoding='utf-8',check=True,timeout=15)
    red = json.loads(next(s.split('COACH_JSON:',1)[1] for s in result.stdout.splitlines() if 'COACH_JSON:' in s))
    assert '0m' in red['hand'] and '5m' not in red['hand']
    assert any(c['tile']=='0m' for c in red['candidates'])
    defensive = present(threatened, 'defence')
    assert defensive['mode']=='defence'
    assert defensive['rates'][defensive['tile']] == min(defensive['rates'].values())
    print('PASS: login/seat, round init, real engine discard, screenshot explanation, riichi risk, round end, stale-result suppression, red five, defence mode.')
finally:
    if previous is None:
        if account_file.exists(): account_file.unlink()
    else:
        account_file.write_bytes(previous)
