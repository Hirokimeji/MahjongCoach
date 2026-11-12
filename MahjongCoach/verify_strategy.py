"""Exercise the compiled engine in an isolated simulated round, without Steam."""
import json
from pathlib import Path
import queue
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from presenter import opponent_rows, present
from strategy import MODES, call_advice, choose, normalized, routes

ROOT = Path(__file__).resolve().parent


def simulate():
    output = queue.Queue()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    with tempfile.TemporaryDirectory() as working:
        engine = subprocess.Popen([str(ROOT/'engine/mahjong-coach-engine.exe'), '-majsoul', '-port', str(port)],
                                  cwd=working, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
        def read():
            for line in engine.stdout:
                if 'COACH_JSON:' in line:
                    output.put(json.loads(line.split('COACH_JSON:', 1)[1]))
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        def send(event, seq, wait=True):
            req = urllib.request.Request(f'https://127.0.0.1:{port}/majsoul',
                data=json.dumps(dict(event, __coach_seq=seq)).encode(), headers={'Content-Type':'application/json'})
            opener.open(req, timeout=5).close()
            if wait:
                while True:
                    state = output.get(timeout=12)
                    if state.get('source_sequence') == seq:
                        return state
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.05)
            send({'account_id':987654321}, 1, False)
            send({'seat_list':[987654321,0,0,0], 'is_game_start':False,
                  'game_config':{'category':1,'mode':{'mode':1}}}, 2, False)
            hand = '2m 4m 5m 2p 3p 4p 5p 6p 7p 4s 5s 6s 7s'.split()
            setup = dict(chang=0, ju=1, ben=0, tiles=hand, doras=['9m'], md5='0'*32,
                         scores=[25000]*4, liqibang=0, left_tile_count=69)
            opening = send(setup, 3)
            assert len(opponent_rows(opening)) == 3
            assert all(status == '待估' for _,status,_ in opponent_rows(opening))
            assert len(opening['hand']) == 13 and not opening['ron_risk']
            initial_waits = {w['tile']: w['remaining'] for w in present(opening)['waits']}
            assert initial_waits['4s'] == 3
            assert present(opening)['routes'] and opening['seat_wind'] != opening['round_wind']
            for seat, tile in enumerate(['9p', '1s', '4s'], 1):
                state = send(dict(seat=seat,tile=tile,is_liqi=seat==3,is_wliqi=False,moqie=False), 3+seat)
                assert len(state['assessed_opponents']) == seat
            assert {w['tile']:w['remaining'] for w in present(state)['waits']}['4s'] == 2
            draw = dict(seat=0,tile='7z',left_tile_count=66,operation={'seat':0,'operation_list':[{'type':1}]})
            state = send(draw, 7)
            opponents = state['opponents']
            assert len(opponents) == 3 and opponents[-1]['riichi'] and opponents[-1]['tenpai'] == 100
            for opponent, discard in zip(opponents,('9p','1s','4s')):
                assert discard not in opponent.get('risk',{})
            for tile, aggregate in state['ron_risk'].items():
                survival = 1
                for opponent in opponents:
                    survival *= 1-opponent.get('risk',{}).get(tile,0)/100
                assert abs(aggregate-100*(1-survival)) < 1e-8
            assert '100%' in opponent_rows(state)[-1][1]
            assert set(state['ron_risk']) == set(map(normalized, state['hand']))
            assert len(state['assessed_opponents']) == 3
            for mode in MODES:
                view = present(state, mode)
                assert view['tile'] in state['hand'] and view['rates'] == state['ron_risk']
                assert view['routes']
            assert present(state)['tile'] == '7z' and len(present(state)['waits']) == 6
            defence = present(state, 'defence')['tile']
            assert state['ron_risk'][normalized(defence)] == min(state['ron_risk'].values())
            dangerous = dict(state, ron_risk=dict(state['ron_risk'], **{'7z':12.5}))
            assert '12.5%' in present(dangerous)['note'] and '高风险' not in present(dangerous,risk_threshold=20)['note']
            actual = send(dict(seat=0,tile='2m',is_liqi=False,is_wliqi=False,moqie=False), 701)
            assert present(actual)['waits'] == state['waits_by_cut']['2m']
            assert present(actual)['tile'] is None
            ended = send({'liujumanguan':False,'scores':[]}, 8)
            assert not present(ended)['hand'] and not present(ended)['routes']
            called_hand = '2m 3m 4m 5m 6m 7m 2s 3s 4s 9p 5z 5z 5z'.split()
            send(dict(setup, tiles=called_hand), 9)
            send(dict(seat=3,tile='5z',is_liqi=False,moqie=False,
                      operation={'seat':0,'operation_list':[{'type':3,'combination':['5z|5z']}]}), 10)
            called = send(dict(seat=0,type=1,tiles=['5z']*3,froms=[0,0,3],
                          operation={'seat':0,'operation_list':[{'type':1,'combination':['5z']}]}), 11)
            assert called['kind']=='discard' and called['open_hand'] and len(called['hand'])==11
            for mode in MODES:
                move = present(called, mode)
                assert move['tile'] in called['hand'] and move['tile'] != '5z'
                assert not {'立直','七对子','平和'} & {p.name for p in move['routes']}
            def offer(tile, operations):
                return dict(seat=3, tile=tile, is_liqi=False, moqie=False,
                            operation=dict(seat=0, operation_list=operations))

            pon_hand = '2m 3m 4m 2s 3s 4s 6p 7p 2z 2z 5z 5z 9s'.split()
            send(dict(setup, tiles=pon_hand), 12)
            pon = send(offer('5z', [dict(type=3, combination=['5z|5z'])]), 13)
            assert present(pon)['title'] == '建议碰白板', pon
            assert '跳过' in present(pon, 'defence')['title']
            chi_hand = '3m 4m 3p 4p 5p 4s 5s 6s 6p 7p 8s 8s 9s'.split()
            send(dict(setup, tiles=chi_hand), 14)
            chi = send(offer('2m', [dict(type=2, combination=['3m|4m'])]), 15)
            assert present(chi)['title'] == '建议吃二万' and '三万、四万' in present(chi)['reason'], chi
            assert '跳过' in present(chi, 'value')['title']

            tenpai = '2m 3m 4m 4p 5p 6p 2s 3s 4s 4m 5m 8p 8p'.split()
            send(dict(setup, tiles=tenpai), 16)
            reach = send(dict(draw, tile='7z', operation=dict(seat=0, operation_list=[
                dict(type=1), dict(type=7, combination=['7z'])])), 17)
            assert present(reach)['title'] == '建议立直 · 打红中', present(reach)
            assert '暂不立直' in present(reach, 'defence')['title']
            send(dict(seat=0, tile='7z', is_liqi=False, moqie=True), 18)
            ron = send(offer('6m', [dict(type=2, combination=['4m|5m']), dict(type=9)]), 19)
            for mode in MODES:
                win = present(ron, mode)
                assert win['title'] == '建议荣和' and '2,000' in win['note'], win
            settle = send(dict(hules=[dict(seat=0, zimo=False, count=2, fu=30, point_rong=2000)],
                               delta_scores=[3300,0,0,-2300]), 20)
            assert '2,000' in present(settle)['reason'] and '+3,300' in present(settle)['note']
            assert not present(settle)['hand']
            send(dict(setup, tiles=tenpai), 21)
            self_win = dict(draw, tile='6m', operation=dict(seat=0, operation_list=[dict(type=8)]))
            tsumo = present(send(self_win, 22))
            assert '建议自摸' == tsumo['title'] and '2,700' in tsumo['note'] and '1,300' in tsumo['note'], tsumo
            send(dict(setup, tiles=tenpai), 23)
            send(dict(draw, tile='7z'), 24)
            send(dict(seat=0, tile='7z', is_liqi=True, moqie=True), 25)
            locked = send(dict(draw, tile='4z'), 26)
            assert locked['kind'] == 'riichi_locked'
            send(dict(seat=0, tile='4z', is_liqi=False, moqie=True), 27)
            reached_win = present(send(self_win, 28))
            assert reached_win['title'] == '建议自摸' and '5,200' in reached_win['note'], reached_win
            kan_hand = '2m 3m 4m 2p 3p 4p 5s 6s 8p 8p 5z 5z 5z'.split()
            waiting = send(dict(setup,tiles=kan_hand),29)
            assert waiting['forecast']['draws']>0 and present(waiting)['forecast']
            kan = send(dict(draw,tile='5z',operation=dict(seat=0,operation_list=[
                dict(type=1),dict(type=4,combination=['5z|5z|5z|5z'])])),30)
            assert present(kan)['title']=='建议暗杠白板', kan
            assert '暂不暗杠' in present(kan,'defence')['note']
            send({'seat_list':[987654321,0,0], 'is_game_start':False,
                  'game_config':{'category':1,'mode':{'mode':11}}},31)
            north_hand = '1m 1m 1m 2p 3p 4p 5s 6s 8p 8p 5z 5z 5z'.split()
            send(dict(setup,tiles=north_hand,scores=[35000]*3,doras=['9s']),32)
            north=send(dict(draw,tile='4z',operation=dict(seat=0,operation_list=[
                dict(type=1),dict(type=11)])),33)
            assert north['players']==3 and present(north)['title']=='建议拔北',north
            assert len(opponent_rows(north)) == 2 and all(p['wind']!='4z' for p in north['opponents'])
            assert present(dict(north,players=4))['title']!='建议拔北'
            orphans = '1m 9m 1p 9p 1s 9s 1z 2z 3z 5z 6z 7z 1z'.split()
            send(dict(setup,tiles=orphans,scores=[35000]*3),34)
            protect=send(dict(draw,tile='4z',operation=dict(seat=0,operation_list=[
                dict(type=1),dict(type=11),dict(type=8)])),35)
            assert present(protect)['title']=='建议自摸'
            avoid = dict(north,special_choices=[
                dict(type=11,tile='4z',before=0,after=1)])
            assert '暂不拔北' in present(avoid)['note']
            send({'seat_list':[987654321,0,0,0], 'is_game_start':False,
                  'game_config':{'category':1,'mode':{'mode':1}}},36)
            send(dict(setup,tiles=kan_hand),37)
            open_kan=send(offer('5z',[dict(type=5,combination=['5z|5z|5z']),dict(type=3,combination=['5z|5z'])]),38)
            assert present(open_kan)['title']=='建议明杠白板',open_kan
            send(dict(seat=0,type=1,tiles=['5z']*3,froms=[0,0,3],
                      operation={'seat':0,'operation_list':[{'type':1,'combination':['5z']}]}),39)
            send(dict(seat=0,tile='8p',is_liqi=False,moqie=False),40)
            added=send(dict(draw,tile='8s',operation=dict(seat=0,operation_list=[
                dict(type=1),dict(type=6,combination=['5z'])])),41)
            assert present(added)['title']=='建议加杠白板',added
            # A complete open shape with no win operation still needs a discard.
            send({'seat_list':[987654321,0,0], 'is_game_start':False,
                  'game_config':{'category':1,'mode':{'mode':11}}},42)
            open_tiles = '0p 5p 7p 8p 3s 4s 5s 6s 7s 8s 2s 2s 7z'.split()
            send(dict(setup, tiles=open_tiles, scores=[35000]*3),43)
            send(dict(seat=2,tile='2s',is_liqi=False,moqie=True),44)
            send(dict(seat=0,type=1,tiles=['2s']*3,froms=[0,0,2],
                      operation=dict(seat=0,operation_list=[dict(type=1,combination=['2s'])])),45)
            send(dict(seat=0,tile='7z',is_liqi=False,moqie=False),46)
            blocked = send(dict(draw,tile='9p',tingpais=[dict(tile='8s',zhenting=True,
                infos=[dict(tile=t,haveyi=False) for t in ('2s','5s','8s')])]),47)
            assert blocked['kind']=='discard' and blocked['win_unavailable']
            cut = next(c for c in blocked['candidates'] if c['tile']=='8s')
            assert cut['furiten']==1 and cut['dama_ukeire']==0
            assert cut['waits'] and all(w['has_yaku'] is False for w in cut['waits'])
            for mode in MODES:
                view = present(blocked, mode)
                assert view['tile'] in blocked['hand'] and '没有和牌按钮' in view['note']
            waiting = send(dict(seat=0,tile='8s',is_liqi=False,moqie=False,zhenting=True),471)
            assert waiting['current_furiten'] and waiting['current_no_yaku']
            assert '振听' in present(waiting)['note'] and '缺役' in present(waiting)['note']
            # Equivalent-looking triplets can be worth keeping or breaking.
            for seq, tiles, drawn, preserve in [
                (48,'2m 3m 4m 2p 2p 7p 8p 9p 4s 5s 6s 1z 7z','2p',True),
                (50,'1m 1m 2m 2m 2p 2p 3s 3s 4s 4s 5z 5z 6z','2p',False)]:
                send({'seat_list':[987654321,0,0,0], 'is_game_start':False,
                      'game_config':{'category':1,'mode':{'mode':1}}},seq*10,False)
                send(dict(setup,tiles=tiles.split()),seq)
                decision = send(dict(draw,tile=drawn),seq+1)
                assert all((choose(decision,m)[0]!='2p')==preserve for m in ('speed','value','avoid_last')), decision
            send(dict(seat_list=[0,987654321,0],is_game_start=False,
                      game_config=dict(category=1,mode=dict(mode=11))),52,False)
            tiles = '2p 2p 4p 9p 3s 3s 5s 3z 4z 5z 7z 7z 7z'.split()
            standings = [57200,34800,13000]
            send(dict(setup,ju=2,tiles=tiles,scores=standings,doras=['4p'],left_tile_count=55),53)
            for seq, seat, tile in [(54,2,'2p'),(55,0,'9m')]:
                send(dict(seat=seat,tile=tile,is_liqi=False,is_wliqi=False,moqie=True),seq)
            decision = send(dict(draw,seat=1,tile='4z',left_tile_count=52,
                                 operation=dict(seat=1,operation_list=[dict(type=1),dict(type=11)])),56)
            decision.update(scores=standings,match_rounds=4)
            cuts = {c['tile']:c for c in decision['candidates']}
            assert cuts['7z']['ukeire']==14 and cuts['9p']['ukeire']==11
            result = present(decision,'avoid_last')
            assert result['tile'] != '7z' and '保留红中刻子' in result['note']
            assert cuts[result['tile']]['normal_shanten']==3 and cuts['7z']['normal_shanten']==4
            print('Sanma yakuhai replay:',result['tile'],cuts[result['tile']]['ukeire'],'live tiles')
            return state
        finally:
            engine.terminate()
            engine.wait(timeout=5)
            reader.join(timeout=2)
            engine.stdout.close()


def check_choices():
    closed = {'round_wind':'1z','seat_wind':'2z'}
    sample = '1m 2m 3m 3m 4m 5m 6m 7m 8m 9m 5z 5z 4z'.split()
    plans = routes(closed, sample)
    assert {'混一色','役牌 · 白板','立直'} <= {p.name for p in plans}
    called = dict(closed, melds=[['1p','2p','3p']], open_hand=True)
    assert not {'混一色','清一色','七对子','对对和','立直','平和','断幺九'} & {p.name for p in routes(called,sample,'平和')}
    pair_hand = '1m 1m 1m 1m 2p 2p 3s 3s 4m 4m 2z 2z 3z'.split()
    assert '5 种对子' in next(p.guide for p in routes(closed,pair_hand) if p.name=='七对子')
    candidates = [dict(tile='5z',shanten=0,ukeire=8,dama_point=1000),
                  dict(tile='4z',shanten=0,ukeire=3,dama_point=8000)]
    snap = dict(closed, hand=sample, candidates=candidates, ron_risk={'5z':6,'4z':4,'1m':0.1})
    assert [choose(snap, m)[0] for m in MODES] == ['5z','4z','1m','5z']
    locked = dict(snap, legal_operations={'operation_list':[{'type':1,'combination':['1m|5z']}]})
    assert all(choose(locked, m)[0]=='4z' for m in MODES)
    opened = dict(snap,open_hand=True,candidates=[
        dict(tile='5z',shanten=0,ukeire=9,dama_ukeire=0,dama_point=0),
        dict(tile='4z',shanten=0,ukeire=2,dama_ukeire=2,dama_point=1000)])
    for mode in ('speed','value','avoid_last'):
        assert choose(opened,mode)[0]=='4z'
        unsafe = dict(opened,candidates=[dict(opened['candidates'][0],furiten=1,dama_ukeire=9),opened['candidates'][1]])
        assert choose(unsafe,mode)[0]=='4z'
        recovery = dict(opened,candidates=[opened['candidates'][0],dict(tile='4z',shanten=1,ukeire=8)])
        assert choose(recovery,mode)[0]=='4z'


def check_shape_and_pressure():
    # Two published 魔女「初期牌效率：搭子」 hands and their suit rotations.
    rotation = str.maketrans('mps','psm')
    for hand, discard in [('12567m55999p2478s','1m'),('24789m35888p3478s','2m')]:
        for _ in range(3):
            output = subprocess.check_output([str(ROOT/'engine/mahjong-coach-engine.exe'), hand],
                                             encoding='utf-8', errors='replace')
            state = json.loads(next(line.split('COACH_JSON:',1)[1] for line in output.splitlines()
                                    if 'COACH_JSON:' in line))
            for mode in ('speed','value','avoid_last'):
                assert choose(state,mode)[0] == discard, (hand,mode)
            hand, discard = hand.translate(rotation), discard.translate(rotation)

    def decision(a,b,mode='speed',**extra):
        return choose(dict(hand=['1m','9p'],candidates=[dict(tile='1m',**a),dict(tile='9p',**b)],**extra),mode)[0]
    wide_now = dict(shanten=2,ukeire=15,next_ukeire=5,improved_ukeire=15)
    develops = dict(shanten=2,ukeire=14,next_ukeire=20,improved_ukeire=17)
    assert decision(wide_now,develops)=='9p'
    assert decision(dict(wide_now,ukeire=25),develops)=='1m'
    assert decision(dict(wide_now,shanten=1),dict(develops,shanten=1))=='1m'
    narrow = dict(shanten=0,ukeire=2,dama_point=8000,win_rate=12)
    wide = dict(shanten=0,ukeire=7,dama_point=3900,win_rate=42)
    assert decision(narrow,wide,'value')=='9p'
    assert decision(narrow,wide,'value',players=3)=='1m'
    assert decision(narrow,dict(wide,win_rate=None),'value')=='1m'
    op = dict(type=3,combination=['5z|5z'])
    call = dict(open_hand=False,offered_tile='5z',shanten=2,hand=['5z','5z','9p','4m'],
                call_choices=[dict(pair=['5z','5z'],discard='9p',shanten=1,ukeire=14,
                                   dama_point=0,furiten=0,part_wait=False)],ron_risk={'9p':7})
    assert call_advice(call,[op],'speed')[0]=='建议碰白板'
    assert '跳过' in call_advice(dict(call,riichi_opponents=['下家']),[op],'speed')[0]
    print('PASS: six shape examples, future efficiency, scoring waits and post-call risk')


if __name__ == '__main__':
    check_choices()
    check_shape_and_pressure()
    demo = simulate()
    if '--save-demo' in sys.argv:
        for key in ('sequence','source_sequence','time'):
            demo.pop(key, None)
        (ROOT/'demo.json').write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: discards, riichi, calls, kan, north, forecasts, ron/tsumo payments, settlement and action priority.')
