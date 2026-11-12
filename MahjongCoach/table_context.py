"""Public score and match-length metadata shared by consecutive game events."""
class TableContext:
    def __init__(self):
        self.scores = None
        self.match_rounds = None

    def update(self, event):
        if 'seat_list' in event:
            self.scores = None
            self.match_rounds = None
            mode = ((event.get('game_config') or {}).get('mode') or {}).get('mode')
            self.match_rounds = {1:4,2:8,11:4,12:8}.get(mode)
        if 'chang' in event and 'ju' in event:
            self.scores = None
            scores = event.get('scores')
            if isinstance(scores,list) and len(scores) in (3,4) and all(type(n) is int for n in scores):
                self.scores = scores.copy()
        # Accepted riichi payments arrive either on their own or with the next action.
        receipt = event.get('liqi') if isinstance(event.get('liqi'),dict) else event
        if self.scores is not None and 'score' in receipt and 'liqibang' in receipt and not receipt.get('failed'):
            seat, score = receipt.get('seat'), receipt['score']
            if type(seat) is int and 0 <= seat < len(self.scores) and type(score) is int:
                self.scores[seat] = score

    def values(self):
        return dict(scores=self.scores.copy() if self.scores is not None else None,
                    match_rounds=self.match_rounds)
