"""Placement policy regression checks using synthetic public table states."""
import json
from pathlib import Path
from strategy import avoid_last_plan, choose
from presenter import present
from table_context import TableContext


def check():
    base = json.loads((Path(__file__).parent/'demo.json').read_text(encoding='utf-8'))
    base.update(scores=[35000,30000,25000,10000],self_seat=0,match_rounds=8,round=7)
    # Leading late is a reason to reduce risk, not automatically abandon a hand.
    assert avoid_last_plan(dict(base,ron_risk={t:0.1 for t in base['ron_risk']}))[0]=='speed'
    assert '领先末位' in present(base,'avoid_last')['placement']
    early = dict(base,round=0,riichi_opponents=['上家'],scores=[28000,25000,24000,23000])
    hand = ['1m','2m','3m']
    good = dict(early,hand=hand,candidates=[
        dict(tile='1m',shanten=1,ukeire=20,dama_point=0,riichi_point=0),
        dict(tile='2m',shanten=2,ukeire=4,dama_point=0,riichi_point=0)],
        ron_risk={'1m':2,'2m':0,'3m':0.1})
    assert choose(good,'avoid_last')[0]=='1m'
    assert avoid_last_plan(good)[0]=='speed'
    push = dict(good,ron_risk={'1m':4.2,'2m':0,'3m':1})
    assert choose(dict(push,wall_remaining=48),'avoid_last')[0]=='1m'
    assert choose(dict(push,wall_remaining=8),'avoid_last')[0]=='2m'
    fold = dict(good,hand=['1m','2m','2m'],ron_risk={'1m':0,'2m':0},
                candidates=[dict(tile='1m',shanten=2,ukeire=24),dict(tile='2m',shanten=2,ukeire=8)])
    assert choose(fold,'defence')[0]=='2m'
    assert choose(dict(fold,riichi_opponents=[]),'defence')[0]=='1m'
    cheap_ready = dict(good,candidates=[
        dict(tile='1m',shanten=0,ukeire=8,dama_point=1000,riichi_point=2000)],
        ron_risk={'1m':5,'2m':0,'3m':0.1})
    assert choose(cheap_ready,'avoid_last')[0]=='1m'
    assert avoid_last_plan(cheap_ready)[0]=='speed'
    weak = dict(good,candidates=[dict(tile='1m',shanten=2,ukeire=4)],ron_risk={'1m':12,'2m':0,'3m':1})
    assert avoid_last_plan(weak)[0]=='defence'
    assert choose(weak,'avoid_last')[0]=='2m'
    quiet = dict(weak,riichi_opponents=[],opponents=[],ron_risk={'1m':0.2,'2m':0,'3m':0.1})
    assert choose(quiet,'avoid_last')[0]=='1m'
    assert avoid_last_plan(dict(good,ron_risk={})) [0]=='speed'
    assert present({'kind':'connected'},'avoid_last')['title']=='等待牌局'
    chase = dict(base,scores=[10000,35000,30000,25000])
    assert avoid_last_plan(chase)[0]=='value'
    close = dict(base,scores=[24000,26000,25000,25000])
    assert avoid_last_plan(close)[0]=='speed'
    tied = dict(base,scores=[25000]*4)
    assert '同点' in avoid_last_plan(tied)[1] and not avoid_last_plan(tied)[2]
    assert '点数信息不足' in avoid_last_plan(dict(base,scores=None))[1]
    assert '点数信息不足' in avoid_last_plan(dict(base,self_seat=None))[1]
    unknown_length = dict(chase,match_rounds=None)
    assert avoid_last_plan(unknown_length)[0]=='speed'
    sanma = dict(chase,players=3,scores=[10000,35000,25000])
    assert present(sanma,'avoid_last')['tag']=='避末'
    # Same-shanten alternatives: a secured yaku is worth a few live tiles,
    # but cannot override a large speed gain, actual tenpai, or real danger.
    for honor in ('5z','6z','7z','1z','3z'):
        split = dict(tile=honor,shanten=2,ukeire=14,normal_shanten=4,normal_ukeire=60)
        keep = dict(tile='9p',shanten=2,ukeire=11,normal_shanten=3,normal_ukeire=51)
        pair_race = dict(sanma,hand=[honor]*3+['9p'],round_wind='1z',seat_wind='3z',
                         candidates=[split,keep],ron_risk={honor:0.05,'9p':0.1},
                         riichi_opponents=[],opponents=[])
        assert choose(pair_race,'avoid_last')[0]=='9p'
        for faster in (dict(split,ukeire=25),dict(split,shanten=0,ukeire=2,dama_point=1600)):
            assert choose(dict(pair_race,candidates=[keep,faster]),'avoid_last')[0]==honor
        assert choose(dict(pair_race,ron_risk={honor:0,'9p':12}),'avoid_last')[0]==honor
        assert choose(dict(pair_race,ron_risk={honor:0,'9p':12}),'defence')[0]==honor
        assert choose(dict(pair_race,candidates=[split,dict(keep,normal_shanten=4)]),'avoid_last')[0]==honor
        assert choose(dict(pair_race,candidates=[split,dict(keep,normal_ukeire=0)]),'avoid_last')[0]==honor
        assert choose(dict(pair_race,legal_operations=dict(operation_list=[dict(type=1,combination=['9p'])])),'avoid_last')[0]==honor
    # Operation priority and kuikae remain in force under the new strategy.
    win = dict(base,legal_operations=dict(seat=0,operation_list=[dict(type=9)]))
    assert present(win,'avoid_last')['title']=='建议荣和'
    blocked = dict(base,legal_operations=dict(seat=0,operation_list=[dict(type=1,combination=['4s'])]))
    assert choose(blocked,'avoid_last')[0]!='4s'
    # Accepted payment, repeated receipt, failure, next round, and new match.
    table = TableContext()
    table.update(dict(seat_list=[1,2,3,4],game_config=dict(mode=dict(mode=2))))
    table.update(dict(chang=0,ju=0,scores=[25000]*4))
    receipt = dict(seat=2,score=24000,liqibang=1)
    table.update(receipt);table.update(receipt)
    assert table.values()['scores']==[25000,25000,24000,25000]
    table.update(dict(receipt,score=0,failed=True))
    assert table.scores[2]==24000
    table.update(dict(chang=0,ju=1,scores=[26000,24000,23000,27000]))
    assert table.scores[2]==23000
    table.update(dict(chang=0,ju=2))
    assert table.scores is None
    table.update(dict(seat_list=[1,2,3]))
    assert table.scores is None and table.match_rounds is None
    import queue
    import threading
    from unittest.mock import Mock
    from backend import Relay
    relay = Relay.__new__(Relay)
    relay.lock, relay.table = threading.Lock(), TableContext()
    relay.sequence, relay.events = 0, queue.Queue()
    relay.engine, relay.stopping = Mock(), threading.Event()
    relay.engine.poll.return_value = None
    relay.latest = dict(kind='connected')
    relay.receive(dict(chang=0,ju=0,scores=[25000]*4))
    relay.latest = dict(kind='waiting',hand=['1m'])
    before = relay.sequence
    relay.receive(receipt)
    state = relay.snapshot()
    assert relay.sequence==before and state['kind']=='waiting'
    assert state['scores']==[25000,25000,24000,25000]
    print('PASS: placement defence/chase, ties, missing data, sanma, legal actions and score receipts')


if __name__=='__main__':
    check()
