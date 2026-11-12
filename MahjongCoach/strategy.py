"""Explain feasible beginner yaku from concealed tiles and fixed groups."""
from collections import Counter
from dataclasses import dataclass

SUITS = {'m': '万', 'p': '筒', 's': '索'}
HONORS = ['东风', '南风', '西风', '北风', '白板', '发财', '红中']
MODES = {'speed': '先胡牌', 'value': '做大牌', 'defence': '先防守', 'avoid_last':'避四'}


def _avoid_last_decision(snapshot):
    scores, seat = snapshot.get('scores'), snapshot.get('self_seat')
    count = snapshot.get('players',4)
    valid_scores = (isinstance(scores,list) and len(scores)==count and type(seat) is int
                    and 0<=seat<count and all(type(n) is int for n in scores))
    ahead, late, gap = False, False, 0
    mode = 'speed'
    if valid_scores:
        mine = scores[seat]
        others = [n for i,n in enumerate(scores) if i!=seat]
        tied = mine in others
        rank = 1+sum(n>mine for n in others)
        ahead = mine>min(others)
        gap = mine-min(others) if ahead else min(others)-mine
        length = snapshot.get('match_rounds')
        late = type(length) is int and snapshot.get('round',0)>=length-2
        standing = f'当前{"并列" if tied else ""}第 {rank} 名'
        standing += f'，领先末位 {gap:,} 点。' if ahead else f'，距上一名 {gap:,} 点。'
        if tied:
            standing += '同点按危险侧处理。'
        if not ahead and late and gap>=8000:
            mode = 'value'
    else:
        standing = '点数信息不足，先结合牌效与风险判断。'

    forbidden = forbidden_discards(snapshot)
    candidates = [c for c in snapshot.get('candidates') or []
                  if c['tile'] in snapshot.get('hand',[]) and normalized(c['tile']) not in forbidden]
    rates = snapshot.get('ron_risk') or {}
    opponents = snapshot.get('opponents') or []
    threats = max(len(snapshot.get('riichi_opponents') or []),
                  sum((p.get('tenpai') or 0)>=45 for p in opponents))

    def budget(candidate):
        shanten, waits = candidate['shanten'], attack_ukeire(snapshot, candidate)
        points = available_points(snapshot, candidate)
        if shanten==0:
            limit = (9 if waits>=4 else 6)+min(4,points/3900*2)
        elif shanten==1:
            limit = 5 if waits>=12 else 3.5
        else:
            limit = 1.5
        if snapshot.get('seat_wind')=='1z':
            limit += 1
        if late and ahead:
            limit *= 0.7 if gap>=8000 else 0.85
        elif late and valid_scores and not ahead:
            limit *= 1.25
        if threats>=2:
            limit *= 0.8
        wall = snapshot.get('wall_remaining')
        if threats and shanten > 0 and isinstance(wall, int) and wall <= count * 3:
            limit *= 0.75
        return limit

    if not candidates:
        if threats and snapshot.get('shanten',0)>=2:
            mode = 'defence'
        tile, candidate = choose(snapshot,mode) if snapshot.get('hand') else (None,None)
        return mode,standing+'等待可用切牌分析，继续按当前牌形判断。',ahead,tile,candidate

    candidates = attacking_choices(snapshot, candidates)
    nearest = min(c['shanten'] for c in candidates)
    forward = [c for c in candidates if c['shanten']==nearest]
    preferred, _ = choose(dict(snapshot,candidates=forward),mode)
    honors = {'5z', '6z', '7z', snapshot.get('round_wind'), snapshot.get('seat_wind')}
    counts = Counter(snapshot['hand'])
    role_cuts = [c for c in forward if nearest > 0 and c['tile'] in honors and counts[c['tile']] == 3]
    def compared_triplet(candidate):
        standard = candidate.get('normal_shanten', 99)
        if (candidate in role_cuts or standard > nearest + 1 or not candidate.get('normal_ukeire')):
            return None
        return max((c for c in role_cuts if standard < c.get('normal_shanten', -1)),
                   key=lambda c:c['ukeire'], default=None)
    def utility(candidate):
        rate = rates.get(normalized(candidate['tile']))
        penalty = (rate/budget(candidate))**1.4 if rate is not None else 1
        outs = progress_score(snapshot, candidate)
        # A secured yaku and a closer standard route can justify giving up a
        # few immediate outs. Keep their value bounded for narrow hands.
        alternative = compared_triplet(candidate)
        credit = min(4, alternative['ukeire']/4) if alternative else 0
        efficiency = min(outs + credit,40)/12
        points = available_points(snapshot, candidate)
        value = min(points,24000)/8000 if mode=='value' and nearest==0 else 0
        return efficiency+value-penalty, candidate['tile']==preferred

    selected = max(forward,key=utility)
    tile = selected['tile']
    risk = rates.get(normalized(tile))
    safe_tile, safe_candidate = choose(snapshot,'defence')
    safe_risk = rates.get(normalized(safe_tile)) if safe_tile else None
    threatened = threats>0 or risk is not None and risk>=8
    # Fold only when advancing actually costs too much risk and a materially
    # safer legal alternative exists. A nominal lead alone never triggers a fold.
    if (threatened and risk is not None and risk>budget(selected) and safe_risk is not None
            and safe_risk<=risk*0.6):
        reason = (f'推进要打{tile_name(tile)}，估计风险 {risk_label(risk)}，'
                  f'超过这手牌的进攻参考线 {budget(selected):.1f}%。'
                  f'改打{tile_name(safe_tile)}，风险 {risk_label(safe_risk)}，本巡退守。')
        return 'defence',standing+reason,ahead,safe_tile,safe_candidate

    shape = '已听牌' if nearest==0 else f'{nearest} 向听'
    risk_text = f'这步风险约 {risk_label(risk)}。' if risk is not None else '这步风险尚待估算。'
    reason = f'{shape}，{selected["ukeire"]} 张有效牌未见。'+risk_text
    alternative = compared_triplet(selected)
    if alternative:
        honor = tile_name(alternative['tile'])
        reason += (f'保留{honor}刻子，普通和牌已有役。拆{honor}有 {alternative["ukeire"]} 张进张，'
                   f'但普通牌形会从 {selected["normal_shanten"]} 向听退到 {alternative["normal_shanten"]} 向听。')
    else:
        reason += '继续保留和牌机会。' if mode=='speed' else '在保留进张的前提下争取追分打点。'
    return mode,standing+reason,ahead,tile,selected


def avoid_last_plan(snapshot):
    mode, reason, ahead, _, _ = _avoid_last_decision(snapshot)
    return mode, reason, ahead


def choose_avoid_last(snapshot):
    _, _, _, tile, candidate = _avoid_last_decision(snapshot)
    return tile, candidate


def forbidden_discards(snapshot):
    return {normalized(t) for op in (snapshot.get('legal_operations') or {}).get('operation_list',[])
            if op['type']==1 for group in op.get('combination') or [] for t in group.split('|')}


def normalized(tile):
    return '5' + tile[1:] if tile.startswith('0') else tile


def riichi_available(snapshot, tile):
    legal = snapshot.get('legal_operations') or {}
    return legal.get('seat') == snapshot.get('self_seat') and any(
        op['type'] == 7 and tile in group.split('|')
        for op in legal.get('operation_list', []) for group in op.get('combination') or [])


def attack_ukeire(snapshot, c):
    if c['shanten'] == 0 and (snapshot.get('open_hand') or c.get('open_hand')):
        return c.get('dama_ukeire', c['ukeire'] if c.get('dama_point') else 0)
    return c['ukeire']


def available_points(snapshot, c):
    points = c.get('dama_point', 0)
    ops = snapshot.get('legal_operations') or {}
    if (not snapshot.get('open_hand') and not c.get('open_hand') and
            (not ops.get('operation_list') or riichi_available(snapshot, c['tile']))):
        points = max(points, c.get('riichi_point', 0))
    return points


def progress_score(snapshot, c):
    outs = attack_ukeire(snapshot, c)
    if c['shanten'] < 2 or not outs:
        return outs
    # For distant hands, allow a small loss now for a wider next step or
    # a draw that improves the shape without changing shanten.
    improvement = max(0, c.get('improved_ukeire', outs) - outs)
    return outs + min(2, c.get('next_ukeire', 0)/10) + min(2, improvement/2)


def attacking_choices(snapshot, candidates):
    # An open hand with no scoring waits may have to go back one step to gain a yaku.
    useful = [c for c in candidates if attack_ukeire(snapshot, c) > 0]
    pool = useful or candidates
    def can_ron(c):
        if c['shanten'] != 0 or c.get('furiten') or not c['ukeire']:
            return False
        return c.get('dama_ukeire', c.get('dama_point', 0)) > 0 or riichi_available(snapshot, c['tile'])
    if any(can_ron(c) for c in pool):
        return [c for c in pool if c['shanten'] != 0 or can_ron(c)]
    return pool


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


def routes(snapshot, hand, hints='', analysis=None):
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
    shape = analysis if analysis is not None else snapshot
    seven_competitive = shape.get('chiitoi_shanten',99) <= shape.get('normal_shanten',99)
    if not fixed and pairs >= 4 and seven_competitive:
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
    risky_cut = None
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
                # Before tenpai, open for a secured yaku or a route at most one
                # replacement away. Two or three floating outsiders are expensive.
                plans = [p for p in plans if p.fit >= (11 if p.name=='清一色' else 10)]
                ready = c['shanten'] == 0
                if ready and (not c['dama_point'] or c['furiten']) or not ready and not plans:
                    continue
                if snapshot.get('riichi_opponents') and not ready:
                    rates = snapshot.get('ron_risk') or {}
                    danger = rates.get(normalized(cut))
                    if danger is not None and danger >= 5:
                        if risky_cut is None or danger < risky_cut[1]:
                            risky_cut = cut,danger
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
    if risky_cut:
        cut,danger = risky_cut
        return '建议跳过吃碰', f'有人立直。吃碰后仍未听牌，还要打{tile_name(cut)}，估计放铳风险 {risk_label(danger)}。'
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
    if snapshot.get('riichi_opponents') and candidate['ukeire'] <= 2 and candidate.get('dama_ukeire',candidate.get('dama_point')):
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
    if mode=='avoid_last':
        return choose_avoid_last(snapshot)
    hand = snapshot['hand']
    candidates = snapshot.get('candidates') or []
    forbidden = forbidden_discards(snapshot)
    candidates = [c for c in candidates if normalized(c['tile']) not in forbidden and c['tile'] in hand]
    if not candidates:
        return None, None
    rates = snapshot.get('ron_risk') or {}
    def efficiency(c):
        breaks = c.get('breaks_triplet', sum(normalized(t)==normalized(c['tile']) for t in hand)==3)
        code = normalized(c['tile'])
        edge = abs(5-int(code[0])) if code[1] != 'z' else 0
        return (-c['shanten'], round(progress_score(snapshot,c),5), attack_ukeire(snapshot,c),
                round(c.get('next_ukeire',0),4), round(c.get('improved_ukeire',0),4),
                -c.get('normal_shanten',99),
                c.get('normal_ukeire',0), not breaks,
                not c.get('discard_dora') and c['tile'][0] != '0', edge, c.get('speed',0))
    if mode == 'defence' and rates:
        # Include every legal tile, even if cutting it dismantles a finished set.
        ranked = {normalized(c['tile']): c for c in candidates}
        legal = [t for t in hand if normalized(t) not in forbidden and normalized(t) in rates]
        preserve_safety = snapshot.get('riichi_opponents') and min(c['shanten'] for c in candidates) >= 2
        def safety(t):
            c = ranked.get(normalized(t))
            reserve = sum(normalized(x)==normalized(t) for x in hand) if rates[normalized(t)]==0 and preserve_safety else 0
            return (-rates[normalized(t)], reserve, efficiency(c) if c else (-99,), t[0] != '0')
        if legal:
            tile = max(legal, key=safety)
            return tile, ranked.get(normalized(tile))
    candidates = attacking_choices(snapshot, candidates)
    fast = max(candidates, key=efficiency)
    if mode != 'value':
        return fast['tile'], fast

    ready = [c for c in candidates if c['shanten']==0]
    has_actions = (snapshot.get('legal_operations') or {}).get('operation_list')
    use_win_rates = snapshot.get('players',4)==4 and all(
        c.get('win_rate') is not None and (not has_actions or snapshot.get('open_hand')
                                           or riichi_available(snapshot,c['tile'])) for c in ready)
    def value(c):
        kept = hand.copy()
        kept.remove(c['tile'])
        plans = routes(snapshot, kept, c.get('yaku', ''), analysis=c)
        fit = max((route_rank(p, 'value') for p in plans), default=0)
        # At tenpai use the engine's point estimate; earlier, use feasible routes.
        points = available_points(snapshot,c)
        # Weight a ready hand's payout by the chance it can actually be
        # collected. The engine's win-rate model is for four players.
        if c['shanten'] == 0 and use_win_rates:
            points *= max(0,min(100,c['win_rate']))/100
        return (points if c['shanten'] == 0 else 0,
                fit - 4 * (c['shanten'] - fast['shanten']) - 2 * bool(c.get('discard_dora') or c['tile'][0] == '0'),
                efficiency(c))
    limit = fast['shanten'] + int(fast['shanten'] >= 2)
    choices = [c for c in candidates if c['shanten'] <= limit and c['ukeire'] > 0]
    best = max(choices, key=value) if choices else fast
    return best['tile'], best
