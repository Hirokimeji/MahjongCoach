"""Placement policy regression checks using synthetic public table states."""
import json
from pathlib import Path
from strategy import avoid_last_plan, choose
from presenter import present
from table_context import TableContext


def check():
    base = json.loads((Path(__file__).parent/'demo.json').read_text(encoding='utf-8'))
    base.update(scores=[35000,30000,25000,10000],self_seat=0,match_rounds=8,round=7)
    assert avoid_last_plan(base)[0]=='defence'
    assert choose(base,'avoid_last')==choose(base,'defence')
    assert '领先末位' in present(base,'avoid_last')['placement']
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
