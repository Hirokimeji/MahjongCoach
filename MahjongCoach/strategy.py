"""Explain feasible beginner yaku from concealed tiles and fixed groups."""
from collections import Counter
from dataclasses import dataclass

SUITS = {'m': '万', 'p': '筒', 's': '索'}
HONORS = ['东风', '南风', '西风', '北风', '白板', '发财', '红中']
MODES = {'speed': '先胡牌', 'value': '做大牌', 'defence': '先防守'}


def normalized(tile):
    return '5' + tile[1:] if tile.startswith('0') else tile


def tile_name(tile):
    if not tile:
        return '等待提示'
    if tile[1] == 'z':
        return HONORS[int(tile[0]) - 1]
    number = '红五' if tile[0] == '0' else '一二三四五六七八九'[int(tile[0]) - 1]
    return number + SUITS[tile[1]]


@dataclass(frozen=True)
class Route:
    name: str
    guide: str
    fit: float
    han: int


def routes(snapshot, hand, hints=''):
    fixed = snapshot.get('melds') or []
    exposed = [normalized(t) for group in fixed for t in group]
    counts = Counter(map(normalized, hand))
    all_tiles = list(counts.elements()) + exposed
    if not all_tiles:
        return []
    opened = snapshot.get('open_hand', False)
    plans = []
    honors = {'5z', '6z', '7z', snapshot.get('round_wind'), snapshot.get('seat_wind')}
    for tile in sorted(honors - {None}):
        held = all_tiles.count(tile)
        if held < 2:
            continue
        unseen = snapshot.get('unseen') or []
        if held == 2 and unseen and unseen[26 + int(tile[0])] == 0:
            continue
        name = tile_name(tile)
        value = 2 if tile == snapshot.get('round_wind') == snapshot.get('seat_wind') else 1
        text = f'已有三张{name}，保住这组就有役，其他牌可灵活吃碰。' if held >= 3 else f'留住这对{name}。再摸到一张或碰成三张，就能靠它有役。'
        plans.append(Route('役牌 · ' + name, text, 13 if held >= 3 else 9, value))
    pairs = sum(n >= 2 for n in counts.values())
    if not fixed and pairs >= 4:
        plans.append(Route('七对子', f'已有 {pairs} 种对子，凑齐七种就能胡。保留对子，全程不吃碰。', pairs + 4, 2))
    triplets = sum(n >= 3 for n in counts.values()) + len(fixed)
    spare_pairs = sum(n == 2 for n in counts.values())
    if all(len(set(map(normalized, group))) == 1 for group in fixed) and triplets >= 1 and triplets + spare_pairs >= 4:
        plans.append(Route('对对和', f'已有 {triplets} 组刻子或杠，另有 {spare_pairs} 对。可以碰，留一对做雀头。', 6 + triplets, 2))
    simples = lambda t: t[1] != 'z' and t[0] not in '19'
    outside = sum(not simples(t) for t in all_tiles)
    if outside <= 3 and all(simples(t) for t in exposed):
        guide = f'手里还有 {outside} 张一、九或字牌，优先替换成二到八的数牌。' if outside else '现在全是二到八的数牌。后面吃碰也只用二到八，就能保留这个役。'
        plans.append(Route('断幺九', guide, 11 - outside, 1))
    for suit, label in SUITS.items():
        same = sum(t[1] == suit for t in all_tiles)
        off = sum(t[1] not in (suit, 'z') for t in all_tiles)
        if same < 7 or off > 3 or any(t[1] not in (suit, 'z') for t in exposed):
            continue
        if any(t[1] == 'z' for t in all_tiles):
            plans.append(Route('混一色', f'已有 {same} 张{label}子。保留{label}子和字牌，逐步换掉其他花色。吃碰后是 2 番。', 11 - off, 2 if opened else 3))
        outsiders = len(all_tiles) - same
        if outsiders <= 3 and all(t[1] == suit for t in exposed):
            plans.append(Route('清一色', f'已有 {same} 张{label}子。把其余花色和字牌换成{label}子，吃碰后是 5 番。', 12 - outsiders, 5 if opened else 6))
    if not opened:
        if not fixed and '平和' in hints:
            plans.append(Route('平和', '保留相邻数牌组成顺子，不吃碰。用非役牌作对子，最后留两面听牌。', 8, 1))
        plans.append(Route('立直', '保持门清，先把相邻的牌凑成组。听牌后看游戏是否亮起「立直」。', 5, 1))
    return plans


def route_rank(plan, mode):
    return plan.fit + (min(plan.han, 6) * 1.3 if mode == 'value' else 0)


def risk_label(rate):
    if rate is None:
        return '待估'
    if rate < 0.1:
        return '<0.1%'
    return f'{rate:.1f}%'


def call_advice(snapshot, actions, mode):
    offered = snapshot.get('offered_tile')
    if mode == 'defence':
        return '建议跳过吃碰', '把手里的牌留作防守，下一巡还能挑安全牌打。'
    before = snapshot.get('shanten')
    if offered is None or before is None:
        return '建议先跳过', '这次缺少吃碰后的牌形分析，先保留手里的组合。'
    best = None
    for op in actions:
        if op['type'] not in (2, 3):
            continue
        verb = '吃' if op['type'] == 2 else '碰'
        for group in op.get('combination') or []:
            pair = group.split('|')
            if len(pair) != 2 or Counter(pair) - Counter(snapshot['hand']):
                continue
            match = sorted(map(normalized, pair))
            for c in snapshot.get('call_choices', []):
                if sorted(c['pair']) != match or c['shanten'] >= before or not c['ukeire']:
                    continue
                kept = snapshot['hand'].copy()
                for t in pair:
                    kept.remove(t)
                cut = next((t for t in kept if t == c['discard']), None)
                if cut is None:
                    cut = next((t for t in kept if normalized(t) == c['discard']), None)
                if cut is None:
                    continue
                kept.remove(cut)
                melds = (snapshot.get('melds') or []) + [pair + [offered]]
                plans = routes(dict(snapshot, melds=melds, open_hand=True), kept)
                # A distant flush or an uncompleted pair alone is a weak reason to open.
                plans = [p for p in plans if p.fit >= 10]
                ready = c['shanten'] == 0
                if ready and (not c['dama_point'] or c['furiten']) or not ready and not plans:
                    continue
                plan = max(plans, key=lambda p: route_rank(p, mode), default=None)
                if mode == 'value' and not snapshot.get('open_hand') and not (
                    (ready and c['dama_point'] >= 3900) or (plan and plan.han >= 2)
                ):
                    continue
                score = (-c['shanten'], c['dama_point'] if mode == 'value' else 0,
                         not c['part_wait'], c['ukeire'], cut[0] != '0')
                if best is None or score > best[0]:
                    how = '、'.join(map(tile_name, pair))
                    benefit = ('接着就听牌了，部分等牌有役。' if c['part_wait'] else '接着就听牌了，有役可以和。') if ready else f'离听牌更近，也能继续做「{plan.name}」。'
                    best = score, f'建议{verb}{tile_name(offered)}', f'用手里的{how}去{verb}，再打{tile_name(cut)}。' + benefit
    if best:
        return best[1:]
    if mode == 'value' and not snapshot.get('open_hand'):
        return '建议跳过吃碰', '这次开门的收益有限，保持门清还能争取立直加番。'
    return '建议跳过吃碰', '这次吃碰没有同时带来更快的进张和清楚的和牌路线。'


def riichi_advice(actions, tile, candidate, mode, snapshot):
    allowed = {t for op in actions if op['type'] == 7
               for group in op.get('combination') or [] for t in group.split('|')}
    if not candidate or candidate['shanten'] != 0 or tile not in allowed:
        return '暂不立直', '按当前打法先切这张，保留换牌的余地。'
    if candidate.get('furiten') or not candidate['ukeire']:
        return '暂不立直', '这手振听或已没有未见的等牌，先留机会换听。'
    if mode == 'defence':
        return '暂不立直', '默听能保留换牌防守的余地。'
    if mode == 'speed' and candidate.get('dama_point', 0) >= 5200 and candidate.get('dama_ukeire') == candidate['ukeire']:
        return '建议默听', '等的牌已有役，默听打点也足够，可以悄悄等别人打出。'
    if snapshot.get('riichi_opponents') and candidate['ukeire'] <= 2:
        return '暂不立直', '已有对手立直，这手至多还剩两张未见的等牌，先留退路。'
    reason = '立直本身就有役，可以等别人打出和牌张。' if not candidate.get('dama_point') else '立直能加番，这手还有机会提高打点。'
    return '建议立直', reason


def special_advice(snapshot, ops, mode):
    names = {4:'暗杠',5:'明杠',6:'加杠',11:'拔北'}
    offered = ops & names.keys()
    if snapshot.get('players') != 3:
        offered = offered - {11}
    if not offered:
        return None
    threats = snapshot.get('riichi_opponents')
    honors = {'5z','6z','7z',snapshot.get('round_wind'),snapshot.get('seat_wind')}
    declines = []
    for c in sorted(snapshot.get('special_choices') or [], key=lambda c:(c['after']-c['before'],c['type']!=11)):
        op,t = c['type'],c['tile']
        if op not in offered:
            continue
        action = names[op]
        reason = ''
        if c['after'] > c['before']:
            reason = '这张牌正帮你凑牌，拿出去会离和牌更远。'
        elif op==11:
            if threats and mode=='defence' and (snapshot.get('ron_risk') or {}).get('4z',1)>0:
                reason = '有人已立直，拔出的北也可能被荣和，先保留更稳。'
            else:
                return True,'建议拔北','取出北风能添一张宝牌，还能补摸一张，当前牌形也能保住。'
        elif threats or mode=='defence':
            reason = '开杠会多翻一张宝牌指示牌，对手也可能加分，先留着这组牌。'
        elif op==5 and not snapshot.get('open_hand') and t not in honors:
            reason = '这个明杠会失去门清，这组牌本身也没有役。'
        elif op==5 and c['after'] >= c['before'] and t not in honors:
            reason = '开杠没有加快听牌，还会多翻一张宝牌指示牌。'
        else:
            return True,'建议'+action+tile_name(t),'这组开杠后能保住牌形，还能补摸一张；新宝牌对全桌有效。'
        declines.append(('暂不'+action,reason))
    return (False, *declines[0]) if declines else (False,'暂不'+names[min(offered)],'暂时缺少操作后的牌形分析。')


def choose(snapshot, mode):
    hand = snapshot['hand']
    candidates = snapshot.get('candidates') or []
    forbidden = set()
    for action in (snapshot.get('legal_operations') or {}).get('operation_list', []):
        if action['type'] == 1:
            for group in action.get('combination') or []:
                forbidden.update(normalized(t) for t in group.split('|'))
    candidates = [c for c in candidates if normalized(c['tile']) not in forbidden and c['tile'] in hand]
    if not candidates:
        return None, None
    rates = snapshot.get('ron_risk') or {}
    def efficiency(c):
        return (-c['shanten'], c['ukeire'], c.get('speed', 0), not c.get('discard_dora'))
    fast = max(candidates, key=efficiency)
    if mode == 'defence' and rates:
        # Include every legal tile, even if cutting it dismantles a finished set.
        ranked = {normalized(c['tile']): c for c in candidates}
        legal = [t for t in hand if normalized(t) not in forbidden and normalized(t) in rates]
        def safety(t):
            c = ranked.get(normalized(t))
            return (-rates[normalized(t)], efficiency(c) if c else (-99, 0, 0, False), t[0] != '0')
        if legal:
            tile = max(legal, key=safety)
            return tile, ranked.get(normalized(tile))
    if mode != 'value':
        return fast['tile'], fast

    def value(c):
        kept = hand.copy()
        kept.remove(c['tile'])
        plans = routes(snapshot, kept, c.get('yaku', ''))
        fit = max((route_rank(p, 'value') for p in plans), default=0)
        # At tenpai use the engine's point estimate; earlier, use feasible routes.
        points = max(c.get('riichi_point', 0), c.get('dama_point', 0))
        return (points if c['shanten'] == 0 else 0,
                fit - 4 * (c['shanten'] - fast['shanten']) - 2 * bool(c.get('discard_dora') or c['tile'][0] == '0'),
                efficiency(c))
    limit = fast['shanten'] + int(fast['shanten'] >= 2)
    choices = [c for c in candidates if c['shanten'] <= limit and c['ukeire'] > 0]
    best = max(choices, key=value) if choices else fast
    return best['tile'], best
