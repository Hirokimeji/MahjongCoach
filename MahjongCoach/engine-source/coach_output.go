package main

// Structured output for the local beginner UI. The upstream analysis ranking is
// preserved; this file exposes facts rather than parsing coloured console text.
import (
	"encoding/json"
	"fmt"
	"github.com/EndlessCheng/mahjong-helper/util"
	"github.com/EndlessCheng/mahjong-helper/util/model"
	"math"
	"sort"
	"time"
)

type coachOperation struct {
	Seat          int `json:"seat"`
	OperationList []struct {
		Type        int      `json:"type"`
		Combination []string `json:"combination"`
	} `json:"operation_list"`
}

var coachCurrent *majsoulRoundData
var coachEmitted bool
var coachSequence int64

// Use only the current hand and unseen tiles, including while opponents act.
func coachImprovingTiles(hand, unseen []int) []map[string]interface{} {
	current := coachShanten(hand)
	waits := []map[string]interface{}{}
	for t, n := range unseen {
		if n <= 0 || hand[t] >= 4 {
			continue
		}
		hand[t]++
		if coachShanten(hand) < current {
			waits = append(waits, map[string]interface{}{"tile": util.Mahjong[t], "remaining": n})
		}
		hand[t]--
	}
	return waits
}

func coachBegin(d *majsoulRoundData) {
	coachCurrent, coachEmitted = d, false
	coachSequence++
}

func coachBase(kind string) map[string]interface{} {
	result := map[string]interface{}{"kind": kind, "sequence": coachSequence, "time": time.Now().UnixMilli(), "engine": "EndlessCheng/mahjong-helper"}
	if d := coachCurrent; d != nil {
		result["source_sequence"] = d.msg.CoachSequence
		result["round"] = d.roundNumber
		result["honba"] = d.benNumber
		result["players"] = d.playerNumber
		result["self_seat"] = d.selfSeat
		reached := []string{}
		for i, p := range d.players {
			if i > 0 && p.isReached {
				reached = append(reached, p.name)
			}
		}
		result["riichi_opponents"] = reached
		if d.msg != nil {
			result["legal_operations"] = d.msg.Operation
		}
		if len(d.counts) == 34 && len(d.players) > 1 && util.CountOfTiles34(d.counts) > 0 {
			p := d.newModelPlayerInfo()
			result["hand"] = coachHand(p)
			result["open_hand"] = p.IsNaki()
			result["round_wind"] = util.Mahjong[p.RoundWindTile]
			result["seat_wind"] = util.Mahjong[p.SelfWindTile]
			result["own_discards"] = len(p.DiscardTiles)
			melds := [][]string{}
			for _, meld := range p.Melds {
				group := []string{}
				for _, t := range meld.Tiles {
					group = append(group, util.Mahjong[t])
				}
				melds = append(melds, group)
			}
			result["melds"] = melds
			result["unseen"] = p.LeftTiles34
			if kind == "waiting" || kind == "discard" {
				hand := append([]int(nil), p.HandTiles34...)
				if util.CountOfTiles34(hand)%3 == 1 {
					result["current_waits"] = coachImprovingTiles(hand, p.LeftTiles34)
				} else if kind == "discard" {
					byCut := map[string]interface{}{}
					for t, count := range hand {
						if count > 0 {
							hand[t]--
							byCut[util.Mahjong[t]] = coachImprovingTiles(hand, p.LeftTiles34)
							hand[t]++
						}
					}
					result["waits_by_cut"] = byCut
				} else if d.players[0].isReached && d.msg.Seat != nil && *d.msg.Seat == d.selfSeat && d.msg.Tile != "" {
					if t, _, err := util.StrToTile34(d.msg.Tile); err == nil && t >= 0 && t < len(hand) && hand[t] > 0 {
						hand[t]--
						result["current_waits"] = coachImprovingTiles(hand, p.LeftTiles34)
					}
				}
			}
			if kind == "waiting" && util.CountOfTiles34(p.HandTiles34)%3 == 1 && d.msg.Hules == nil && d.msg.Liujumanguan == nil {
				result["forecast"] = coachForecast(p, d.playerNumber, -1)
				if !p.IsNaki() && d.playerNumber == 4 && coachShanten(p.HandTiles34) == 0 {
					_, waits := util.CalculateShantenAndWaits13(p.HandTiles34, p.LeftTiles34)
					if len(waits) > 0 {
						result["win_rate"] = util.CalculateAvgAgariRate(waits, p)
					}
				}
			}
			if op := d.msg.Operation; op != nil && op.Seat == d.selfSeat {
				result["special_choices"] = coachSpecial(d, p)
				for _, action := range op.OperationList {
					if action.Type == 8 || action.Type == 9 {
						result["win_score"] = coachWinScore(d, p, action.Type == 8)
						break
					}
				}
			}
			if kind == "waiting" || kind == "discard" {
				rates, included, opponents := coachRonRates(d)
				result["ron_risk"], result["assessed_opponents"], result["opponents"] = rates, included, opponents
			}
		}
	}
	return result
}

func coachWinScore(d *majsoulRoundData, p *model.PlayerInfo, tsumo bool) map[string]interface{} {
	code := d.msg.Tile
	if code == "" && !tsumo {
		code, _ = d.msg.Tiles.(string) // Robbing a kan.
	}
	tile, red, err := util.StrToTile34(code)
	if err != nil || tile < 0 || tile >= 34 {
		return nil
	}
	p.WinTile, p.IsTsumo = tile, tsumo
	p.IsDaburii = d.players[0].isDoubleReach
	if !tsumo {
		p.HandTiles34 = append([]int(nil), p.HandTiles34...)
		p.HandTiles34[tile]++
		if red {
			p.NumRedFives = append([]int(nil), p.NumRedFives...)
			p.NumRedFives[tile/9]++
		}
	}
	if util.CountOfTiles34(p.HandTiles34)+3*len(p.Melds) != 14 || p.HandTiles34[tile] < 1 {
		return nil
	}
	score := util.CalcPoint(p)
	if score.Point <= 0 {
		return nil
	}
	han, fu, yakuman := score.Breakdown()
	if yakuman == 0 && p.IsRiichi && d.players[0].canIppatsu {
		han++
	}
	child, parent := util.CalcPointTsumo(han, fu, yakuman, p.IsParent)
	return map[string]interface{}{
		"han": han, "fu": fu, "yakuman": yakuman, "dealer": p.IsParent,
		"ron": util.CalcPointRon(han, fu, yakuman, p.IsParent), "child": child, "parent": parent,
	}
}

// Estimate the chance of ron, excluding point-loss and dora value multipliers.
// Combine observed opponents with an independence approximation. A completely
// unobserved opponent contributes no estimate; the UI displays coverage.
type coachOpponent struct {
	Name   string             `json:"name"`
	Wind   string             `json:"wind"`
	Riichi bool               `json:"riichi"`
	Tenpai *float64           `json:"tenpai,omitempty"`
	Risk   map[string]float64 `json:"risk,omitempty"`
}

func coachRonRates(d *majsoulRoundData) (map[string]float64, []string, []coachOpponent) {
	survival := [34]float64{}
	for i := range survival {
		survival[i] = 1
	}
	included := []string{}
	opponents := []coachOpponent{}
	infos := d.analysisTilesRisk()
	for who, player := range d.players {
		if who == 0 || (d.playerNumber == 3 && player.selfWindTile == 30) {
			continue
		}
		turns := len(player.discardTiles)
		row := coachOpponent{Name: player.name, Wind: util.Mahjong[player.selfWindTile], Riichi: player.isReached}
		if turns == 0 && !player.isReached && !player.isNaki {
			opponents = append(opponents, row)
			continue
		}
		if turns < 1 {
			turns = 1
		}
		info := infos[who]
		conditional := util.CalculateRiskTiles34(util.MinInt(turns, util.MaxTurns),
			info.safeTiles34, d.leftCounts, nil, d.roundWindTile, player.selfWindTile).
			FixWithEarlyOutside(player.earlyOutsideTiles)
		included = append(included, player.name)
		tenpai := math.Max(0, math.Min(100, info.tenpaiRate))
		row.Tenpai, row.Risk = &tenpai, map[string]float64{}
		for tile, rate := range conditional {
			chance := math.Min(1, math.Max(0, rate*tenpai/10000))
			survival[tile] *= 1 - chance
			if chance > 0 && d.leftCounts[tile]+d.counts[tile] > 0 && !(d.playerNumber == 3 && tile >= 1 && tile <= 7) {
				row.Risk[util.Mahjong[tile]] = 100 * chance
			}
		}
		opponents = append(opponents, row)
	}
	result := map[string]float64{}
	if len(included) > 0 {
		for tile, count := range d.counts {
			if count > 0 {
				result[util.Mahjong[tile]] = 100 * (1 - survival[tile])
			}
		}
	}
	return result, included, opponents
}

func coachWrite(result map[string]interface{}) {
	data, err := json.Marshal(result)
	if err != nil {
		return
	}
	fmt.Println("COACH_JSON:" + string(data))
	coachEmitted = true
}

func coachHand(p *model.PlayerInfo) []string {
	reds := append([]int(nil), p.NumRedFives...)
	for _, m := range p.Melds {
		if m.ContainRedFive && len(m.Tiles) > 0 && m.Tiles[0] < 27 {
			reds[m.Tiles[0]/9]--
		}
	}
	hand := []string{}
	for tile, count := range p.HandTiles34 {
		for n := 0; n < count; n++ {
			code := util.Mahjong[tile]
			if tile < 27 && tile%9 == 4 && n < reds[tile/9] {
				code = "0" + code[1:]
			}
			hand = append(hand, code)
		}
	}
	return hand
}

func coachCandidate(r *util.Hand14AnalysisResult, risk riskTable, p *model.PlayerInfo) map[string]interface{} {
	a := r.Result13
	waits := []map[string]interface{}{}
	for _, tile := range a.Waits.AvailableTiles() {
		waits = append(waits, map[string]interface{}{"tile": util.Mahjong[tile], "remaining": a.Waits[tile]})
	}
	yakuIDs := []int{}
	for y := range a.YakuTypes {
		yakuIDs = append(yakuIDs, y)
	}
	sort.Ints(yakuIDs)
	code := util.Mahjong[r.DiscardTile]
	for _, t := range coachHand(p) {
		if t == code {
			goto normalFiveFound
		}
	}
	if r.DiscardTile < 27 && r.DiscardTile%9 == 4 {
		code = "0" + code[1:]
	}
normalFiveFound:
	result := map[string]interface{}{
		"tile": code, "name": util.MahjongZH[r.DiscardTile], "shanten": a.Shanten,
		"ukeire": a.Waits.AllCount(), "waits": waits, "yaku": util.YakuTypesToStr(yakuIDs),
		"furiten": a.FuritenRate, "part_wait": a.IsPartWait, "open_hand": a.IsNaki,
		"speed": a.MixedWaitsScore, "next_ukeire": a.AvgNextShantenWaitsCount,
		"dama_point": a.DamaPoint, "riichi_point": a.RiichiPoint, "discard_dora": r.IsDiscardDoraTile,
		"dama_ukeire": a.DamaWaits.AllCount(),
		"win_rate":    a.AvgAgariRate,
		"open_tiles":  r.OpenTiles,
	}
	if risk != nil {
		result["risk"] = risk[r.DiscardTile]
	}
	return result
}

func coachEmit14(p *model.PlayerInfo, shanten int, results, backwards util.Hand14AnalysisResultList, risk riskTable) {
	result := coachBase("discard")
	result["hand"] = coachHand(p)
	if shanten < 0 {
		result["kind"] = "complete"
		coachWrite(result)
		return
	}
	if len(results) == 0 {
		result["kind"] = "waiting"
		coachWrite(result)
		return
	}
	candidates := []map[string]interface{}{}
	for _, r := range results {
		candidates = append(candidates, coachCandidate(r, risk, p))
	}
	result["candidates"] = candidates
	best := 0
	if shanten == 1 && len(p.DiscardTiles) < 9 && !p.IsNaki() && len(backwards) > 0 && results[0].Result13.Waits.AllCount() < 9 && results[0].Result13.MixedWaitsScore < backwards[0].Result13.MixedWaitsScore {
		// Match the upstream simpleBestDiscardTile early-hand exception.
		candidates = append(candidates, coachCandidate(backwards[0], risk, p))
		best = len(candidates) - 1
		result["candidates"] = candidates
		result["backward_improvement"] = true
	}
	result["best_index"] = best
	if coachCurrent != nil {
		cut := results[0].DiscardTile
		if best != 0 {
			cut = backwards[0].DiscardTile
		}
		result["forecast"] = coachForecast(p, coachCurrent.playerNumber, cut)
	}
	for _, r := range backwards {
		if best != 0 && r == backwards[0] {
			continue
		}
		candidates = append(candidates, coachCandidate(r, risk, p))
	}
	result["candidates"] = candidates
	if risk != nil {
		safe := []map[string]interface{}{}
		for tile, count := range p.HandTiles34 {
			if count > 0 {
				safe = append(safe, map[string]interface{}{"tile": util.Mahjong[tile], "risk": risk[tile]})
			}
		}
		sort.SliceStable(safe, func(i, j int) bool { return safe[i]["risk"].(float64) < safe[j]["risk"].(float64) })
		result["defence"] = safe
	}
	coachWrite(result)
}

func coachEmit13(p *model.PlayerInfo, a *util.Hand13AnalysisResult) {
	result := coachBase("waiting")
	result["hand"] = coachHand(p)
	result["shanten"] = a.Shanten
	coachWrite(result)
}

// Reuse the pass and post-call analyses calculated for this discard.
func coachEmitCalls(pass *util.Hand13AnalysisResult, results, backwards util.Hand14AnalysisResultList) {
	d := coachCurrent
	if d == nil || d.msg.Operation == nil || d.msg.Operation.Seat != d.selfSeat || d.msg.Moqie == nil {
		return
	}
	for _, op := range d.msg.Operation.OperationList {
		if op.Type != 2 && op.Type != 3 {
			continue
		}
		state := coachBase("waiting")
		state["offered_tile"] = d.msg.Tile
		state["shanten"] = pass.Shanten
		choices := []map[string]interface{}{}
		for _, list := range []util.Hand14AnalysisResultList{results, backwards} {
			for _, r := range list {
				a := r.Result13
				pair := []string{}
				for _, t := range r.OpenTiles {
					pair = append(pair, util.Mahjong[t])
				}
				choices = append(choices, map[string]interface{}{
					"pair": pair, "discard": util.Mahjong[r.DiscardTile], "shanten": a.Shanten,
					"ukeire": a.Waits.AllCount(), "dama_point": a.DamaPoint, "furiten": a.FuritenRate,
					"part_wait": a.IsPartWait,
				})
			}
		}
		state["call_choices"] = choices
		coachWrite(state)
		return
	}
}

func coachEmitError(err error) {
	result := coachBase("error")
	result["message"] = "游戏数据暂时无法解析，请从新的一局开始，或查看本地日志。"
	coachWrite(result)
}

func coachAfter(d *majsoulRoundData) {
	if coachEmitted {
		return
	}
	if op := d.msg.Operation; op != nil && op.Seat == d.selfSeat && len(d.counts) == 34 &&
		util.CountOfTiles34(d.counts)%3 == 2 && len(d.players) > 0 && !d.players[0].isReached {
		for _, action := range op.OperationList {
			if action.Type == 1 {
				p := d.newModelPlayerInfo()
				shanten, results, backwards := util.CalculateShantenWithImproves14(p)
				coachEmit14(p, shanten, results, backwards, nil)
				return
			}
		}
	}
	result := coachBase("waiting")
	if d.msg.Hules != nil || d.msg.Liujumanguan != nil {
		result["kind"] = "round_end"
		for _, h := range d.msg.Hules {
			if h.Seat == d.selfSeat {
				settlement := map[string]interface{}{"tsumo": h.Zimo, "dealer": h.Qinjia,
					"han": h.Count, "fu": h.Fu, "yiman": h.Yiman, "ron": h.PointRong,
					"child": h.PointZimoXian, "parent": h.PointZimoQin, "sum": h.PointSum}
				if h.Seat >= 0 && h.Seat < len(d.msg.DeltaScores) {
					settlement["delta"] = d.msg.DeltaScores[h.Seat]
				}
				result["settlement"] = settlement
				break
			}
		}
	} else if len(d.players) > 0 && d.players[0].isReached {
		result["kind"] = "riichi_locked"
	}
	if gameConf.currentActiveMajsoulAccountID < 0 {
		result["kind"] = "need_login"
	}
	coachWrite(result)
}
