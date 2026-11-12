"""Chinese coaching text shared by the live view and the example."""
from strategy import MODES, attack_ukeire, avoid_last_plan, call_advice, choose, normalized, riichi_advice, risk_label, route_rank, routes, special_advice, tile_name


def forecast_text(snapshot, candidate=None):
    rate = snapshot.get('win_rate')
    if candidate and candidate['shanten']==0:
        rate = candidate.get('win_rate')
    if rate is not None and snapshot.get('players',4)==4:
        method = '按当前副露' if snapshot.get('open_hand') else '按门清立直'
        return f'听牌和率约 {min(100,max(0,rate)):.0f}%（{method}估算，含荣和、自摸）。'
    f = snapshot.get('forecast')
    if not f:
        return ''
    lead = ('模拟先打'+tile_name(f['cut'])+'，') if f.get('cut') else ''
    chance = f'约 {100*f["wins"]/f["trials"]:.0f}%' if f['wins'] else f'{f["trials"]} 次模拟均未自摸'
    return f'{lead}未来 {f["draws"]} 次摸牌的自摸机会：{chance}。假设无人提前和牌，期间不吃碰。'


def payment(score, tsumo, players):
    if not tsumo:
        points = score.get('ron', 0)
        return f'放铳者付 {points:,} 点' if points else ''
    child, parent = score.get('child', 0), score.get('parent', 0)
    if child and score.get('dealer'):
        return f'每家付 {child:,} 点，共 {child*(players-1):,} 点'
    if child and parent:
        return f'庄家付 {parent:,} 点，另有 {players-2} 家各付 {child:,} 点，共 {parent+child*(players-2):,} 点'
    return ''


def score_text(score, tsumo, players):
    parts = []
    if score.get('yakuman'):
        parts.append('役满' if score['yakuman'] == 1 else f'{score["yakuman"]} 倍役满')
    elif score.get('yiman'):
        parts.append('役满')
    elif score.get('han'):
        parts.append(f'{score["han"]} 番' + (f' {score["fu"]} 符' if score.get('fu') else ''))
    pay = payment(score, tsumo, players)
    if pay:
        parts.append(pay)
    elif score.get('sum'):
        parts.append(f'{score["sum"]:,} 点')
    return ' · '.join(parts)


def shanten_text(number):
    if number == 0:
        return '打出后就听牌了。'
    if number == 1:
        return '打出后离听牌还差一次有效进张。'
    return f'打出后离听牌还差至少 {number} 次有效进张。'


def opponent_rows(snapshot, hand_only=True):
    hand = {normalized(t) for t in snapshot.get('hand') or []}
    rows = []
    for player in snapshot.get('opponents') or []:
        wind = tile_name(player['wind'])
        seat = wind if snapshot.get('players') == 3 else f'{player["name"]}（{wind}）'
        rate = player.get('tenpai')
        if rate is None:
            rows.append((seat,'待估','等这家有弃牌或副露后再看。'))
            continue
        status = '已立直 · 100%' if player['riichi'] else f'约 {risk_label(rate)}'
        risks = player.get('risk') or {}
        tiles = sorted((t for t in risks if not hand_only or t in hand),
                       key=lambda t:(-risks[t], 'mpsz'.index(t[-1]), t[0]))
        danger = '　'.join(f'{tile_name(t)} {risk_label(risks[t])}' for t in tiles[:3])
        rows.append((seat,status,danger or '当前范围内没有筛出危险牌。'))
    return rows


def _present(snapshot, strategy='speed', risk_threshold=5, selection=None, cautious=False):
    kind = snapshot.get('kind', 'connected')
    hand = snapshot.get('hand') or []
    active = kind in ('waiting', 'discard', 'riichi_locked', 'complete') and bool(hand)
    result = dict(title='等待牌局', tag='准备就绪', tile=None, waits=[], hand=hand if active else [],
                  reason='启动雀魂进入新一局，或点「看截图示例」试试三种打法。', next_title='有效进张',
                  note='', detail='', mode='waiting', alternatives=[], routes=[], rates={}, risk_caption='', forecast='')
    if not active:
        settled = snapshot.get('settlement')
        if kind == 'round_end' and settled:
            tsumo = settled['tsumo']
            delta = settled.get('delta')
            result.update(title='你自摸了' if tsumo else '你荣和了', tag='雀魂结算',
                          reason=score_text(settled, tsumo, snapshot.get('players', 4)) or '本次和牌已确认。',
                          note=f'雀魂结算点数变动：{delta:+,} 点' if delta is not None else '')
            return result
        messages = {
            'round_end': ('本局结束', '等下一局发牌，再一起看起手方向。'),
            'processing': ('正在读牌', '正在分析最新动作。'),
            'need_login': ('等待识别座位', '登录后请从新的一局开始。'),
            'error': ('提示已暂停', snapshot.get('message') or '请从新的一局重新开始。'),
        }
        if kind in messages:
            result['title'], result['reason'] = messages[kind]
            result['tag'] = '牌局状态'
        return result
    rates = snapshot.get('ron_risk') or {}
    assessed = snapshot.get('assessed_opponents') or []
    count = snapshot.get('players', 4) - 1
    if rates and len(assessed) == count:
        caption = '打出这张牌，至少一名对手荣和的粗估概率。'
    elif rates:
        caption = '仅估算' + '、'.join(assessed) + '的荣和风险，其余对手还缺少弃牌信息。'
    else:
        caption = '牌河信息不足，每张牌先标「待估」。'
    result.update(rates=rates, risk_caption=caption, tag=MODES[strategy])
    if 'current_waits' in snapshot:
        result.update(waits=snapshot['current_waits'], next_title='当前手牌的有效进张')
    legal = snapshot.get('legal_operations') or {}
    if legal.get('seat') != snapshot.get('self_seat'):
        legal = {}
    actions = legal.get('operation_list') or []
    ops = {op['type'] for op in actions}
    if 8 in ops or 9 in ops:
        tsumo = 8 in ops
        score = score_text(snapshot.get('win_score') or {}, tsumo, snapshot.get('players', 4))
        why = '已经摸到和牌张，建议收下这手。' if tsumo else '对手打出了你能和的牌，建议现在收下；跳过会进入振听。'
        result.update(title='建议自摸' if tsumo else '建议荣和', reason=why, mode='win',
                      note=('牌面估算：' + score + '（未计本场、供托和额外番）') if score else '这手暂时无法估分，和牌后显示雀魂结算。')
        return result
    result['forecast'] = forecast_text(snapshot)
    special = special_advice(snapshot, ops, 'defence' if cautious else strategy)
    if special and (special[0] or kind=='riichi_locked'):
        result.update(title=special[1], reason=special[2])
        return result
    if kind in ('complete', 'riichi_locked'):
        result.update(title='当前没有和牌操作' if kind == 'complete' else '你已立直',
                      reason='请按游戏当前亮起的操作继续。' if kind == 'complete' else '等待和牌张。')
        if snapshot.get('current_furiten'):
            result['note'] = '当前振听，不能荣和。'
        return result
    tile, candidate = choose(snapshot, selection or strategy) if kind == 'discard' else (None, None)
    kept = hand.copy()
    if tile:
        kept.remove(tile)
    hints = candidate.get('yaku', '') if candidate else ''
    plans = sorted(routes(snapshot, kept, hints, analysis=candidate), key=lambda p: route_rank(p, strategy), reverse=True)
    result['routes'] = plans[:2]
    if not tile:
        result.update(title='这手可以从这里做起' if snapshot.get('own_discards') == 0 else '等下一次摸牌',
                      reason='先看下面的役种方向，轮到你出牌时会亮出推荐牌。')
        if kind == 'waiting' and ops & {2, 3}:
            title, reason = call_advice(snapshot, actions, strategy)
            result.update(title=title, reason=reason, mode='call')
            if special:
                result['note'] = special[1]+'。'+special[2]
        elif special:
            result.update(title=special[1], reason=special[2])
        elif kind == 'discard' and 7 in ops:
            result.update(title='暂缓立直', reason='这次缺少切牌分析，请先查看游戏标出的立直候选牌。')
        if snapshot.get('current_no_yaku') or snapshot.get('current_furiten'):
            messages = []
            if snapshot.get('current_furiten'):
                messages.append('当前振听，不能荣和。')
            if snapshot.get('current_no_yaku'):
                messages.append('当前未见的待牌都缺役，下一巡优先换出有役的听口。')
            result['note'] = ' '.join(messages)
        return result
    name = tile_name(tile)
    result.update(tile=tile, title='打 ' + name, mode='defence' if strategy == 'defence' else 'attack')
    blocked = {normalized(t) for op in legal.get('operation_list', []) if op['type'] == 1
               for group in op.get('combination') or [] for t in group.split('|')}
    result['alternatives'] = [c for c in snapshot.get('candidates', [])
                              if c['tile'] != tile and normalized(c['tile']) not in blocked][:3]
    step = shanten_text(candidate['shanten']) if candidate else '这步可能需要拆开已有的组合。'
    if (strategy == 'defence' or candidate is None) and rates:
        result['reason'] = f'在当前能估算的对手中，{name}的放铳估计最低（{risk_label(rates.get(normalized(tile)))}）。' + step
    elif strategy == 'value':
        points = max(candidate.get('riichi_point', 0), candidate.get('dama_point', 0))
        if points:
            result['reason'] = f'保留听牌，按引擎估算，和牌时平均打点约 {points:.0f} 点。'
        elif plans:
            result['reason'] = f'这张打掉后，可以朝「{plans[0].name}」做。' + step
        else:
            result['reason'] = '这手还看不出容易做大的役，先保留进张。' + step
    else:
        prefix = '开局风险暂时待估，先按进张选牌。' if strategy == 'defence' else ''
        if tile.endswith('z') and hand.count(tile) == 1:
            prefix += f'{name}只有一张。'
        result['reason'] = prefix + step + f'能让手牌前进的牌还有 {candidate["ukeire"]} 张未见。'
    alerts = []
    if snapshot.get('riichi_opponents'):
        alerts.append('、'.join(snapshot['riichi_opponents']) + '已立直')
    if snapshot.get('win_unavailable'):
        alerts.append('牌形已凑齐，本巡没有和牌按钮，仍需出牌。')
    if candidate and candidate['shanten'] == 0:
        if candidate.get('furiten'):
            alerts.append('打出后振听，所有待牌都不能荣和。')
        if candidate.get('open_hand') or snapshot.get('open_hand'):
            scoring = attack_ukeire(snapshot, candidate)
            if candidate['ukeire'] and not scoring:
                alerts.append('当前待牌无役，通常自摸也不能和，接下来要换听或补役。')
                if strategy != 'defence':
                    result['reason'] = '这步只能保住听牌形。' + (plans[0].guide if plans else '下一次摸牌时再比较有役的换听。')
            elif scoring < candidate['ukeire']:
                alerts.append(f'部分待牌无役，未见的待牌中只有 {scoring} 张有役。')
        elif not candidate.get('dama_ukeire', candidate.get('dama_point')) and candidate['ukeire']:
            alerts.append('默听缺役；保持门清可以靠自摸得役。')
    elif candidate and candidate.get('furiten', 0) > 0:
        alerts.append('部分后续进张可能形成振听。')
    result['note'] = ' · '.join(alerts)
    result['forecast'] = forecast_text(snapshot,candidate)
    if candidate:
        result.update(waits=candidate.get('waits') or [], next_title='听牌后等这些牌' if candidate['shanten'] == 0 else '下一步想摸到',
                      detail=step + f' 有效牌共 {candidate["ukeire"]} 张未见，其中也可能有牌在别人手里。')
    else:
        result['detail'] = '这次以防守为先，引擎没有提供这张切牌的进张明细。'
    if 7 in ops and not snapshot.get('open_hand'):
        riichi_mode = 'defence' if cautious and candidate and candidate.get('dama_point') else strategy
        advice, reason = riichi_advice(actions, tile, candidate, riichi_mode, snapshot)
        result.update(title=f'{advice} · 打{name}', reason=reason)
    if special:
        result['note'] = ' '.join(filter(None,(special[1]+'。'+special[2],result['note'])))
    after_cut = snapshot.get('waits_by_cut', {}).get(normalized(tile))
    if after_cut is not None and not candidate:
        result.update(waits=after_cut, next_title=f'打{name}后的有效进张',
                      detail=f'选择防守切牌后，剩余手牌有 {sum(w["remaining"] for w in after_cut)} 张有效牌未见。')
    rate = rates.get(normalized(tile))
    if rate is not None and rate >= risk_threshold:
        warning = f'高风险 · 打{name}的放铳风险估计为 {risk_label(rate)}'
        if len(assessed) < count:
            warning += '（仅含已评估对手）'
        safer, _ = choose(snapshot, 'defence')
        if safer and rates.get(normalized(safer), rate) < rate:
            warning += f'。想防守可打{tile_name(safer)}，约 {risk_label(rates[normalized(safer)])}'
        result['note'] = '  '.join(filter(None, (warning, result['note'])))
    return result


def present(snapshot, strategy='speed', risk_threshold=5):
    if strategy != 'avoid_last':
        return _present(snapshot,strategy,risk_threshold)
    mode, explanation, ahead = avoid_last_plan(snapshot)
    result = _present(snapshot,mode,risk_threshold,selection='avoid_last',cautious=mode=='defence')
    result['tag'] = '避末' if snapshot.get('players')==3 else MODES[strategy]
    if result['hand']:
        result['placement'] = explanation
        result['note'] = '  '.join(filter(None,(explanation,result['note'])))
    return result
