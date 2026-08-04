// alphacore — native hot-path core for the Alpha Zero engine.
//
// Bit-exact port of the Python finance hot paths (CPython's MT19937 +
// cached Box-Muller gaussian, MarketSimulator, Monte Carlo forecast,
// strategy comparison, stress tests) so that native runs are drop-in
// replacements for the pure-Python implementations.
//
// Protocol: JSON object on stdin, JSON object on stdout.
// Commands: forecast | market | compare | stress | benchmark
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"sort"
	"time"
)

// ---------------------------------------------------------------------------
// CPython-compatible RNG (MT19937 + genrand_res53 + cached gauss)
// ---------------------------------------------------------------------------

const (
	mtN          = 624
	mtM          = 397
	mtMatrixA    = 0x9908b0df
	mtUpperMask  = 0x80000000
	mtLowerMask  = 0x7fffffff
	mtInitFactor = 0x6c078965
)

type RNG struct {
	mt        [mtN]uint32
	index     int
	gaussNext *float64
}

// NewRNG seeds exactly like CPython's random.Random(int seed):
// init_genrand(19650218) then init_by_array with the 32-bit little-endian
// words of the integer.
func NewRNG(seed int64) *RNG {
	r := &RNG{index: mtN}
	words := intToWords(seed)
	r.initByArray(words)
	return r
}

func intToWords(seed int64) []uint32 {
	// CPython converts the seed int into 32-bit words, little-endian.
	if seed == 0 {
		return []uint32{0}
	}
	var words []uint32
	for seed != 0 {
		words = append(words, uint32(seed)&0xffffffff)
		seed >>= 32
	}
	return words
}

func (r *RNG) initGenrand(s uint32) {
	r.mt[0] = s
	for i := 1; i < mtN; i++ {
		r.mt[i] = mtInitFactor*(r.mt[i-1]^(r.mt[i-1]>>30)) + uint32(i)
	}
	r.index = mtN
}

func (r *RNG) initByArray(key []uint32) {
	r.initGenrand(19650218)
	i, j := 1, 0
	k := len(key)
	if mtN > k {
		k = mtN
	}
	for ; k > 0; k-- {
		r.mt[i] = (r.mt[i] ^ ((r.mt[i-1] ^ (r.mt[i-1] >> 30)) * 1664525)) + key[j] + uint32(j)
		i++
		j++
		if j >= len(key) {
			j = 0
		}
		if i >= mtN {
			r.mt[0] = r.mt[mtN-1]
			i = 1
		}
	}
	for k = mtN - 1; k > 0; k-- {
		r.mt[i] = (r.mt[i] ^ ((r.mt[i-1] ^ (r.mt[i-1] >> 30)) * 1566083941)) - uint32(i)
		i++
		if i >= mtN {
			r.mt[0] = r.mt[mtN-1]
			i = 1
		}
	}
	r.mt[0] = mtUpperMask
}

func (r *RNG) nextInt32() uint32 {
	if r.index >= mtN {
		for i := 0; i < mtN-mtM; i++ {
			x := (r.mt[i] & mtUpperMask) | (r.mt[i+1] & mtLowerMask)
			r.mt[i] = r.mt[i+mtM] ^ (x >> 1) ^ (x & 1 * mtMatrixA)
		}
		for i := mtN - mtM; i < mtN-1; i++ {
			x := (r.mt[i] & mtUpperMask) | (r.mt[i+1] & mtLowerMask)
			r.mt[i] = r.mt[i+mtM-mtN] ^ (x >> 1) ^ (x & 1 * mtMatrixA)
		}
		x := (r.mt[mtN-1] & mtUpperMask) | (r.mt[0] & mtLowerMask)
		r.mt[mtN-1] = r.mt[mtM-1] ^ (x >> 1) ^ (x & 1 * mtMatrixA)
		r.index = 0
	}
	y := r.mt[r.index]
	r.index++
	y ^= y >> 11
	y ^= (y << 7) & 0x9d2c5680
	y ^= (y << 15) & 0xefc60000
	y ^= y >> 18
	return y
}

// Float64 is genrand_res53: (a*67108864.0 + b) / 9007199254740992.0
func (r *RNG) Float64() float64 {
	a := r.nextInt32() >> 5
	b := r.nextInt32() >> 6
	return (float64(a)*67108864.0 + float64(b)) / 9007199254740992.0
}

// Gauss replicates random.Random.gauss including the cached-second-value
// behavior, which affects the exact RNG consumption pattern.
func (r *RNG) Gauss(mu, sigma float64) float64 {
	z := r.gaussNext
	r.gaussNext = nil
	if z == nil {
		x2pi := r.Float64() * 2 * math.Pi
		g2rad := math.Sqrt(-2.0 * math.Log(1.0-r.Float64()))
		z1 := math.Cos(x2pi) * g2rad
		s := math.Sin(x2pi) * g2rad
		r.gaussNext = &s
		z = &z1
	}
	return mu + *z*sigma
}

// ---------------------------------------------------------------------------
// MarketSimulator port
// ---------------------------------------------------------------------------

type MarketYear struct {
	Year         int     `json:"year"`
	Sp500Return  float64 `json:"sp500_return"`
	BondReturn   float64 `json:"bond_return"`
	Inflation    float64 `json:"inflation"`
	FedRate      float64 `json:"fed_rate"`
	GDPGrowth    float64 `json:"gdp_growth"`
	Unemployment float64 `json:"unemployment"`
	Regime       string  `json:"regime"`
}

func round4(x float64) float64 {
	return math.Round(x*10000) / 10000
}

type MarketSim struct {
	rng *RNG
}

func NewMarketSim(seed int64) *MarketSim {
	return &MarketSim{rng: NewRNG(seed)}
}

func (m *MarketSim) determineRegime(year int) string {
	cyclePos := (year - 2026) % 15
	shock := m.rng.Float64()
	if shock < 0.05 {
		return "crisis"
	} else if cyclePos < 8 {
		return "bull"
	} else if cyclePos < 10 {
		return "bear"
	}
	return "stagnant"
}

func (m *MarketSim) generateYear(year int) MarketYear {
	regime := m.determineRegime(year)
	var sp500Mult, bondMult, inflationAdj, fedAdj, gdpMult, unemploymentAdj float64
	switch regime {
	case "bull":
		sp500Mult, bondMult, inflationAdj, fedAdj, gdpMult, unemploymentAdj = 1.5, 0.8, -0.005, 0.005, 1.3, -0.01
	case "bear":
		sp500Mult, bondMult, inflationAdj, fedAdj, gdpMult, unemploymentAdj = -0.5, 1.3, 0.01, -0.01, 0.5, 0.02
	case "stagnant":
		sp500Mult, bondMult, inflationAdj, fedAdj, gdpMult, unemploymentAdj = 0.3, 1.0, 0.0, 0.0, 0.7, 0.005
	default: // crisis
		sp500Mult, bondMult, inflationAdj, fedAdj, gdpMult, unemploymentAdj = -1.5, 1.5, 0.02, -0.02, -0.5, 0.04
	}
	sp500Return := 0.10*sp500Mult + m.rng.Gauss(0, 0.15)
	bondReturn := 0.04*bondMult + m.rng.Gauss(0, 0.05)
	inflation := 0.025 + inflationAdj + m.rng.Gauss(0, 0.01)
	if inflation < 0 {
		inflation = 0
	}
	fedRate := 0.03 + fedAdj + m.rng.Gauss(0, 0.005)
	if fedRate < 0 {
		fedRate = 0
	}
	gdpGrowth := 0.025*gdpMult + m.rng.Gauss(0, 0.01)
	unemployment := 0.05 + unemploymentAdj + m.rng.Gauss(0, 0.005)
	if unemployment < 0.02 {
		unemployment = 0.02
	} else if unemployment > 0.15 {
		unemployment = 0.15
	}
	return MarketYear{
		Year:         year,
		Sp500Return:  round4(sp500Return),
		BondReturn:   round4(bondReturn),
		Inflation:    round4(inflation),
		FedRate:      round4(fedRate),
		GDPGrowth:    round4(gdpGrowth),
		Unemployment: round4(unemployment),
		Regime:       regime,
	}
}

func (m *MarketSim) years(start, count int) []MarketYear {
	cache := make(map[int]MarketYear)
	out := make([]MarketYear, 0, count)
	for i := 0; i < count; i++ {
		y := start + i
		v, ok := cache[y]
		if !ok {
			v = m.generateYear(y)
			cache[y] = v
		}
		out = append(out, v)
	}
	return out
}

// ---------------------------------------------------------------------------
// Request / response types
// ---------------------------------------------------------------------------

type StrategySpec struct {
	Name        string             `json:"name"`
	DisplayName string             `json:"display_name"`
	Allocations map[string]float64 `json:"allocations"`
	ExpectedRet float64            `json:"expected_return"`
	Volatility  float64            `json:"volatility"`
	Sharpe      float64            `json:"sharpe_target"`
}

type ForecastRequest struct {
	InitialValue float64 `json:"initial_value"`
	ExpectedRet  float64 `json:"expected_return"`
	Volatility   float64 `json:"volatility"`
	Years        int     `json:"years"`
	Paths        int     `json:"paths"`
	Seed         int64   `json:"seed"`
}

type MarketRequest struct {
	Seed   int64 `json:"seed"`
	Years  int   `json:"years"`
	Start  int   `json:"start_year"`
	Series bool  `json:"series"` // series=true: consume RNG sequentially per year
}

type CompareRequest struct {
	InitialValue  float64        `json:"initial_value"`
	Years         int            `json:"years"`
	MarketReturns []float64      `json:"market_returns"`
	Strategies    []StrategySpec `json:"strategies"`
	Seed          int64          `json:"seed"`
}

type StressRequest struct {
	InitialValue float64            `json:"initial_value"`
	Strategy     string             `json:"strategy"`
	Allocations  map[string]float64 `json:"allocations"`
	Volatility   float64            `json:"volatility"`
	Scenarios    map[string]map[string]float64 `json:"scenarios"`
}

type BenchmarkRequest struct {
	Seed    int64 `json:"seed"`
	Years   int   `json:"years"`
	Paths   int   `json:"paths"`
	Rounds  int   `json:"rounds"`
	Initial float64 `json:"initial_value"`
}

func fail(err error) {
	writeJSON(map[string]any{"error": err.Error()})
	os.Exit(1)
}

func writeJSON(v any) {
	b, _ := json.Marshal(v)
	os.Stdout.Write(b)
	os.Stdout.Write([]byte("\n"))
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

func cmdForecast(req ForecastRequest) {
	years := max(1, req.Years)
	paths := max(10, req.Paths)
	vol := req.Volatility
	expected := req.ExpectedRet

	marketSim := NewMarketSim(req.Seed)
	marketYears := marketSim.years(2026, years)

	rng := NewRNG(req.Seed)
	finalValues := make([]float64, 0, paths)
	series := make([][]float64, paths)
	for p := 0; p < paths; p++ {
		value := req.InitialValue
		s := make([]float64, 0, years+1)
		s = append(s, value)
		for i := 0; i < years; i++ {
			marketReturn := marketYears[i].Sp500Return
			strategyReturn := marketReturn*(expected/0.10) + rng.Gauss(0, vol*0.3)
			value *= 1 + strategyReturn
			if value < 0 {
				value = 0
			}
			s = append(s, math.Round(value*100)/100)
		}
		finalValues = append(finalValues, value)
		series[p] = s
	}

	sorted := make([]float64, len(finalValues))
	copy(sorted, finalValues)
	sort.Float64s(sorted)

	percentiles := map[string]float64{}
	for _, pct := range []float64{5, 25, 50, 75, 95} {
		idx := int((pct / 100.0) * float64(len(sorted)-1))
		percentiles[fmt.Sprintf("p%d", int(pct))] = math.Round(sorted[idx]*100) / 100
	}

	mean := 0.0
	for _, v := range finalValues {
		mean += v
	}
	mean /= float64(len(finalValues))
	median := sorted[len(sorted)/2]
	if len(sorted)%2 == 0 {
		median = (sorted[len(sorted)/2-1] + sorted[len(sorted)/2]) / 2
	}
	probLoss := 0.0
	for _, v := range finalValues {
		if v < req.InitialValue {
			probLoss++
		}
	}
	probLoss /= float64(len(finalValues))

	writeJSON(map[string]any{
		"initial_value": req.InitialValue,
		"years":         years,
		"paths":         len(finalValues),
		"seed":          req.Seed,
		"percentiles":   percentiles,
		"mean_value":    math.Round(mean*100) / 100,
		"median_value":  math.Round(median*100) / 100,
		"prob_of_loss":  math.Round(probLoss*10000) / 10000,
		"worst_path":    math.Round(sorted[0]*100) / 100,
		"best_path":     math.Round(sorted[len(sorted)-1]*100) / 100,
		"median_return_pct": math.Round((median/req.InitialValue-1)*100*100) / 100,
	})
}

func cmdMarket(req MarketRequest) {
	marketSim := NewMarketSim(req.Seed)
	out := make([]MarketYear, 0, req.Years)
	if req.Series {
		out = marketSim.years(req.Start, req.Years)
	} else {
		cache := map[int]MarketYear{}
		for i := 0; i < req.Years; i++ {
			y := req.Start + i
			v, ok := cache[y]
			if !ok {
				v = marketSim.generateYear(y)
				cache[y] = v
			}
			out = append(out, v)
		}
	}
	writeJSON(map[string]any{"market": out})
}

func cmdCompare(req CompareRequest) {
	rng := NewRNG(req.Seed)
	results := map[string]any{}
	for _, strat := range req.Strategies {
		value := req.InitialValue
		annual := make([]float64, 0, req.Years)
		for i := 0; i < req.Years; i++ {
			yearReturn := req.MarketReturns[i]
			portfolioReturn := 0.0
			for asset, weight := range strat.Allocations {
				portfolioReturn += weight * yearReturn * sensitivity(asset)
			}
			portfolioReturn += rng.Gauss(0, strat.Volatility*0.3)
			value *= 1 + portfolioReturn
			annual = append(annual, portfolioReturn)
		}
		totalReturn := (value/req.InitialValue - 1) * 100
		avg := 0.0
		for _, a := range annual {
			avg += a
		}
		avg /= float64(len(annual))
		results[strat.Name] = map[string]any{
			"name":                 strat.DisplayName,
			"final_value":          value,
			"total_return_pct":     math.Round(totalReturn*100) / 100,
			"annualized_return_pct": math.Round(avg*100*100) / 100,
			"volatility":           strat.Volatility,
			"sharpe_target":        strat.Sharpe,
		}
	}
	writeJSON(map[string]any{"results": results})
}

func sensitivity(asset string) float64 {
	switch asset {
	case "tech_stocks":
		return 1.5
	case "leveraged_etf":
		return 2.0
	case "crypto":
		return 2.5
	case "emerging_markets":
		return 1.3
	case "us_stocks":
		return 1.0
	case "intl_stocks":
		return 0.9
	case "bonds":
		return 0.3
	case "real_estate":
		return 0.7
	case "consumer_staples":
		return 0.6
	case "gold":
		return 0.2
	case "utilities":
		return 0.5
	case "dividend_stocks":
		return 0.8
	case "reits":
		return 0.7
	case "preferred_stock":
		return 0.4
	case "cash":
		return 0.02
	}
	return 1.0
}

func cmdStress(req StressRequest) {
	results := make([]map[string]any, 0, len(req.Scenarios))
	for scenario, shocks := range req.Scenarios {
		portfolioShock := 0.0
		for asset, weight := range req.Allocations {
			s := shocks[asset]
			if s == 0 && shocks[asset] == 0 {
				if _, ok := shocks[asset]; !ok {
					s = -0.2
				}
			}
			portfolioShock += weight * s
		}
		affected := req.InitialValue * (1 + portfolioShock)
		results = append(results, map[string]any{
			"scenario":       scenario,
			"portfolio_shock": math.Round(portfolioShock*10000) / 10000,
			"value_after":    math.Round(affected*100) / 100,
			"loss":           math.Round((req.InitialValue-affected)*100) / 100,
		})
	}
	sort.Slice(results, func(i, j int) bool {
		return results[i]["portfolio_shock"].(float64) < results[j]["portfolio_shock"].(float64)
	})
	writeJSON(map[string]any{
		"strategy":        req.Strategy,
		"initial_value":   req.InitialValue,
		"volatility":      req.Volatility,
		"scenarios":       results,
		"worst_scenario":  results[0]["scenario"],
		"best_scenario":   results[len(results)-1]["scenario"],
	})
}

func cmdBenchmark(req BenchmarkRequest) {
	start := time.Now()
	marketSim := NewMarketSim(req.Seed)
	marketYears := marketSim.years(2026, req.Years)
	rng := NewRNG(req.Seed)
	for r := 0; r < req.Rounds; r++ {
		value := req.Initial
		for p := 0; p < req.Paths; p++ {
			value = req.Initial
			for i := 0; i < req.Years; i++ {
				strategyReturn := marketYears[i].Sp500Return + rng.Gauss(0, 0.12*0.3)
				value *= 1 + strategyReturn
			}
		}
	}
	elapsed := time.Since(start)
	writeJSON(map[string]any{
		"rounds":    req.Rounds,
		"paths":     req.Paths,
		"years":     req.Years,
		"elapsed_ms": elapsed.Milliseconds(),
		"runs":      req.Rounds * req.Paths,
	})
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

func main() {
	cmd := "forecast"
	if len(os.Args) > 1 {
		cmd = os.Args[1]
	}

	raw, err := io.ReadAll(os.Stdin)
	if err != nil {
		fail(err)
	}
	if len(raw) == 0 {
		raw = []byte("{}")
	}

	switch cmd {
	case "forecast":
		var req ForecastRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdForecast(req)
	case "market":
		var req MarketRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdMarket(req)
	case "compare":
		var req CompareRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdCompare(req)
	case "stress":
		var req StressRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdStress(req)
	case "benchmark":
		var req BenchmarkRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdBenchmark(req)
	default:
		writeJSON(map[string]any{"error": "unknown command: " + cmd})
		os.Exit(1)
	}
}
