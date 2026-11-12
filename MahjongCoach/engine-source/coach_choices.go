package main

import (
	"math/rand"
	"strings"

	"github.com/EndlessCheng/mahjong-helper/util"
	"github.com/EndlessCheng/mahjong-helper/util/model"
)

// The upstream shanten routine covers ordinary hands and seven pairs.
func coachShanten(hand []int) int {
	sh := util.CalculateShanten(hand)
	if util.CountOfTiles34(hand) < 13 {
		return sh
	}
	distinct, pair := 0, 0
	for _, i := range []int{0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33} {
		if hand[i] > 0 {
			distinct++
		}
		if hand[i] >= 2 {
			pair = 1
		}
	}
	return util.MinInt(sh, 13-distinct-pair)
}

func coachSpecial(d *majsoulRoundData, p *model.PlayerInfo) []map[string]interface{} {
	choices := []map[string]interface{}{}
	hand := append([]int(nil), p.HandTiles34...)
	before := coachShanten(hand)
	for _, op := range d.msg.Operation.OperationList {
		var targets []int
		remove := 0
		switch op.Type {
		case 4, 6: // concealed or added kan
			remove = 4
			if op.Type == 6 {
				remove = 1
			}
			for t, n := range hand {
				if n < remove {
					continue
				}
				if op.Type == 6 {
					pon := false
					for _, m := range p.Melds {
						if m.MeldType == model.MeldTypePon && m.Tiles[0] == t {
							pon = true
						}
					}
					if !pon {
						continue
					}
				}
				allowed := len(op.Combination) == 0
				for _, group := range op.Combination {
					for _, code := range strings.Split(group, "|") {
						i, _, err := util.StrToTile34(code)
						if err == nil && i == t {
							allowed = true
						}
					}
				}
				if allowed {
					targets = append(targets, t)
				}
			}
		case 5: // open kan on an opponent's discard
			t, _, err := util.StrToTile34(d.msg.Tile)
			if err == nil && t >= 0 && t < 34 {
				targets = []int{t}
			}
			remove = 3
		case 11: // sanma north extraction
			if d.playerNumber == 3 {
				targets = []int{30}
			}
			remove = 1
		default:
			continue
		}
		for _, t := range targets {
			if hand[t] < remove {
				continue
			}
			hand[t] -= remove
			after := coachShanten(hand)
			hand[t] += remove
			choices = append(choices, map[string]interface{}{"type": op.Type, "tile": util.Mahjong[t], "before": before, "after": after})
		}
	}
	return choices
}

// Finite-horizon self-draw simulation. All unseen tiles are exchangeable,
// opponents do not call or end the hand, and the simulated player never calls.
func coachForecast(p *model.PlayerInfo, players int, cut int) map[string]interface{} {
	base := append([]int(nil), p.HandTiles34...)
	if cut >= 0 {
		base[cut]--
	}
	if util.CountOfTiles34(base)%3 != 1 || players < 3 {
		return nil
	}
	horizon := util.MinInt(6, p.LeftDrawTilesCount/players)
	if horizon <= 0 {
		return nil
	}
	pool := util.Tiles34ToTiles(p.LeftTiles34)
	if len(pool) < horizon {
		return nil
	}
	const trials = 160
	wins := 0
	cache := map[[34]uint8]int{}
	shanten := func(hand []int) int {
		var key [34]uint8
		for i, n := range hand {
			key[i] = uint8(n)
		}
		if v, ok := cache[key]; ok {
			return v
		}
		v := coachShanten(hand)
		cache[key] = v
		return v
	}
	rng := rand.New(rand.NewSource(173))
	for trial := 0; trial < trials; trial++ {
		hand := append([]int(nil), base...)
		stock := append([]int(nil), pool...)
		step := shanten(hand)
		for n := 0; n < horizon && step < horizon-n; n++ {
			i := n + rng.Intn(len(stock)-n)
			stock[n], stock[i] = stock[i], stock[n]
			draw := stock[n]
			hand[draw]++
			if step == 0 && shanten(hand) < 0 {
				info := *p
				info.HandTiles34, info.IsTsumo, info.WinTile = hand, true, draw
				if !info.IsNaki() || util.CalcPoint(&info).Point > 0 {
					wins++
					break
				}
			}
			discard := draw
			if !p.IsRiichi {
				best, weakest := 99, 99
				for t, count := range hand {
					if count == 0 {
						continue
					}
					hand[t]--
					value := shanten(hand)
					support := 2 * hand[t]
					if t < 27 {
						for _, offset := range []int{-2, -1, 1, 2} {
							j := t + offset
							if j >= 0 && j < 27 && j/9 == t/9 && hand[j] > 0 {
								support++
							}
						}
					}
					hand[t]++
					if value < best || (value == best && support < weakest) {
						best, weakest, discard = value, support, t
					}
				}
				step = best
			}
			hand[discard]--
		}
	}
	result := map[string]interface{}{"draws": horizon, "wins": wins, "trials": trials}
	if cut >= 0 {
		result["cut"] = util.Mahjong[cut]
	}
	return result
}
