// alphacore — native hot-path core for the Alpha Zero engine.
//
// Bit-exact port of the Python finance hot paths (CPython's MT19937 +
// cached Box-Muller gaussian, MarketSimulator, Monte Carlo forecast,
// strategy comparison, stress tests) so that native runs are drop-in
// replacements for the pure-Python implementations.
//
// Protocol: JSON object on stdin, JSON object on stdout.
// Commands: forecast | market | compare | stress | benchmark
//
//	| interview | coach | analyze | narrate | memory (Phase 6 AI)
//	| advisor_financial | advisor_health | advisor_mentor (Phase 8 advisors)
package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	_ "github.com/go-sql-driver/mysql"
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
	InitialValue float64                       `json:"initial_value"`
	Strategy     string                        `json:"strategy"`
	Allocations  map[string]float64            `json:"allocations"`
	Volatility   float64                       `json:"volatility"`
	Scenarios    map[string]map[string]float64 `json:"scenarios"`
}

type BenchmarkRequest struct {
	Seed    int64   `json:"seed"`
	Years   int     `json:"years"`
	Paths   int     `json:"paths"`
	Rounds  int     `json:"rounds"`
	Initial float64 `json:"initial_value"`
}

// ---------------------------------------------------------------------------
// Phase 6: AI agent command requests (interview | coach | analyze | narrate | memory)
//
// These commands expose the JSON protocol consumed by the Rust MCP client and
// MCP server. The Go core provides deterministic baseline handling; the Rust
// client bridges to the Python AI agents for the full LLM-powered behavior.
// ---------------------------------------------------------------------------

type InterviewRequest struct {
	Name        string `json:"name"`
	Age         int    `json:"age"`
	Gender      string `json:"gender"`
	InitialText string `json:"initial_interview_text"`
	Workspace   string `json:"workspace"`
	Repo        string `json:"repo"`
}

type CoachingRequest struct {
	Workspace     string `json:"workspace"`
	CharacterJSON string `json:"character_json"`
	Situation     string `json:"situation"`
	Repo          string `json:"repo"`
	SessionID     string `json:"session_id"`
}

type AnalyzeRequest struct {
	Workspace         string          `json:"workspace"`
	SimulationResults []SimulationRes `json:"simulation_results"`
	Repo              string          `json:"repo"`
}

type SimulationRes struct {
	FinalNetWorth  float64 `json:"final_net_worth"`
	FinalHappiness float64 `json:"final_happiness"`
	FinalAge       int     `json:"final_age"`
}

type NarrateRequest struct {
	Workspace        string        `json:"workspace"`
	CharacterName    string        `json:"character_name"`
	SimulationResult SimulationRes `json:"simulation_result"`
	Repo             string        `json:"repo"`
}

type MemoryRequest struct {
	Workspace string         `json:"workspace"`
	Operation string         `json:"operation"` // store | retrieve | update | delete | create_session
	Data      map[string]any `json:"data"`
	Query     string         `json:"query"`
	SessionID string         `json:"session_id"`
	Repo      string         `json:"repo"`
}

// ReportRequest — durable persistence of simulation reports against a
// MySQL-wire-compatible store (TiDB default, port 4000). Mirrors the
// behaviour of the Python infra.tidb_store layer so native runs and Python
// runs share the same tables.
type ReportRequest struct {
	Operation string `json:"operation"` // health | store | load | list
	ReportID  string `json:"report_id"`
	RunType   string `json:"run_type"`
	Config    any    `json:"config"`
	Report    any    `json:"report"`
	Backend   string `json:"backend"`
	Limit     int    `json:"limit"`
	DSN       string `json:"dsn"` // override ALPHA_ZERO_SQL_DSN
}

const reportSchema = `
CREATE TABLE IF NOT EXISTS simulation_reports (
    id           VARCHAR(64)  PRIMARY KEY,
    run_type     VARCHAR(32)  NOT NULL,
    config       JSON         NOT NULL,
    report       JSON         NOT NULL,
    backend      VARCHAR(16)  DEFAULT 'go',
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    KEY idx_reports_type (run_type),
    KEY idx_reports_created (created_at)
);`

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
		"initial_value":     req.InitialValue,
		"years":             years,
		"paths":             len(finalValues),
		"seed":              req.Seed,
		"percentiles":       percentiles,
		"mean_value":        math.Round(mean*100) / 100,
		"median_value":      math.Round(median*100) / 100,
		"prob_of_loss":      math.Round(probLoss*10000) / 10000,
		"worst_path":        math.Round(sorted[0]*100) / 100,
		"best_path":         math.Round(sorted[len(sorted)-1]*100) / 100,
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
			"name":                  strat.DisplayName,
			"final_value":           value,
			"total_return_pct":      math.Round(totalReturn*100) / 100,
			"annualized_return_pct": math.Round(avg*100*100) / 100,
			"volatility":            strat.Volatility,
			"sharpe_target":         strat.Sharpe,
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
			"scenario":        scenario,
			"portfolio_shock": math.Round(portfolioShock*10000) / 10000,
			"value_after":     math.Round(affected*100) / 100,
			"loss":            math.Round((req.InitialValue-affected)*100) / 100,
		})
	}
	sort.Slice(results, func(i, j int) bool {
		return results[i]["portfolio_shock"].(float64) < results[j]["portfolio_shock"].(float64)
	})
	writeJSON(map[string]any{
		"strategy":       req.Strategy,
		"initial_value":  req.InitialValue,
		"volatility":     req.Volatility,
		"scenarios":      results,
		"worst_scenario": results[0]["scenario"],
		"best_scenario":  results[len(results)-1]["scenario"],
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
		"rounds":     req.Rounds,
		"paths":      req.Paths,
		"years":      req.Years,
		"elapsed_ms": elapsed.Milliseconds(),
		"runs":       req.Rounds * req.Paths,
	})
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// ---------------------------------------------------------------------------
// Phase 6: AI agent commands
//
// Deterministic baseline handlers. The Rust MCP client replaces these with
// the full Python AI agent implementations via `python3 ai/<agent>.py`.
// ---------------------------------------------------------------------------

func cmdInterview(req InterviewRequest) {
	profile := map[string]any{
		"name":             firstNonEmpty(req.Name, "Unknown"),
		"age":              req.Age,
		"gender":           firstNonEmpty(req.Gender, "male"),
		"happiness":        50,
		"health":           70,
		"smarts":           50,
		"looks":            50,
		"karma":            50,
		"occupation":       "unknown",
		"education":        "unknown",
		"birthplace":       "Unknown",
		"current_city":     "Unknown",
		"social_variables": map[string]int{},
		"desires":          map[string]float64{},
	}
	writeJSON(map[string]any{
		"status":  "success",
		"backend": "go",
		"profile": profile,
		"persona": profile,
		"message": "baseline profile from Go core; use Rust client for full AI extraction",
	})
}

func cmdCoach(req CoachingRequest) {
	character := map[string]any{}
	if req.CharacterJSON != "" {
		if err := json.Unmarshal([]byte(req.CharacterJSON), &character); err != nil {
			character = map[string]any{}
		}
	}
	advice := map[string]any{
		"character_name": firstNonEmpty(str(character["name"]), "Unknown"),
		"situation":      firstNonEmpty(req.Situation, "general"),
		"analysis": map[string]any{
			"overall_health":  "baseline",
			"immediate_focus": []string{"Build consistent daily habits"},
		},
		"recommendations": []string{
			"Invest in health and learning consistently",
			"Build a diversified financial portfolio",
			"Maintain strong relationships and community ties",
		},
		"action_plan": map[string]any{
			"immediate_steps":  []string{"Sleep 7-9 hours", "Save 20% of income"},
			"short_term_goals": []string{"Build an emergency fund", "Learn a new skill"},
			"long_term_vision": "Create sustainable wealth and wellbeing",
		},
		"encouragement": "Keep building momentum — small consistent steps compound.",
		"message":       "baseline advice from Go core; use Rust client for full AI coaching",
	}
	writeJSON(map[string]any{"status": "success", "backend": "go", "result": advice})
}

func cmdAnalyze(req AnalyzeRequest) {
	total := len(req.SimulationResults)
	avgNW, avgHap := 0.0, 0.0
	if total > 0 {
		for _, r := range req.SimulationResults {
			avgNW += r.FinalNetWorth
			avgHap += r.FinalHappiness
		}
		avgNW /= float64(total)
		avgHap /= float64(total)
	}
	analysis := map[string]any{
		"simulation_results": req.SimulationResults,
		"summary": map[string]any{
			"total":         total,
			"avg_net_worth": math.Round(avgNW*100) / 100,
			"avg_happiness": math.Round(avgHap*100) / 100,
		},
		"recommendations": []string{
			"Balanced paths (wealth + happiness) are most achievable",
			"Maintain diversified investments across regimes",
		},
		"message": "baseline analysis from Go core; use Rust client for full AI analysis",
	}
	writeJSON(map[string]any{"status": "success", "backend": "go", "result": analysis})
}

func cmdNarrate(req NarrateRequest) {
	narrative := map[string]any{
		"character_name": firstNonEmpty(req.CharacterName, "Unknown"),
		"age":            req.SimulationResult.FinalAge,
		"title":          "The Story of " + firstNonEmpty(req.CharacterName, "Unknown"),
		"opening":        "Every life holds countless parallel paths.",
		"development":    []string{},
		"climax":         "The turning point arrived when choices became consequences.",
		"resolution":     "A new chapter begins.",
		"key_insights":   []string{"Every choice shapes the future"},
		"message":        "baseline narrative from Go core; use Rust client for full AI storytelling",
	}
	writeJSON(map[string]any{"status": "success", "backend": "go", "result": narrative})
}

func cmdMemory(req MemoryRequest) {
	switch req.Operation {
	case "store":
		learningID := firstNonEmpty(str(req.Data["learning_id"]), "unknown")
		writeJSON(map[string]any{
			"status":  "success",
			"backend": "go",
			"result":  map[string]any{"learning_id": learningID, "stored": true},
			"message": "baseline memory store; use Rust client for full persistence",
		})
	case "retrieve":
		writeJSON(map[string]any{
			"status":  "success",
			"backend": "go",
			"result":  map[string]any{"results": []any{}, "count": 0},
			"message": "baseline memory retrieve; use Rust client for full recall",
		})
	default:
		writeJSON(map[string]any{
			"status":  "success",
			"backend": "go",
			"result":  map[string]any{"operation": req.Operation, "accepted": true},
			"message": "baseline memory operation; use Rust client for full implementation",
		})
	}
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if v != "" {
			return v
		}
	}
	return ""
}

// ---------------------------------------------------------------------------
// Phase 8: Advisor commands (advisor_financial | advisor_health | advisor_mentor)
//
// Deterministic ports of the Python advisor heuristic cores — the exact
// OLLAMA_DISABLE=1 path of ai/financial_advisor.py, ai/health_coach.py and
// ai/mentor.py — so native runs produce the same advice JSON as the Python
// agents in deterministic mode. The Rust MCP client replaces these baselines
// with the full Python AI agents (including LLM personalization).
// ---------------------------------------------------------------------------

type AdvisorRequest struct {
	CharacterJSON json.RawMessage `json:"character_json"`
	Character     json.RawMessage `json:"character"`
	Situation     string          `json:"situation"`
	Question      string          `json:"question"`
}

// character returns the parsed character dict, honoring both the
// character_json and character keys (string or object form).
func (req AdvisorRequest) character() map[string]any {
	raw := req.CharacterJSON
	if len(raw) == 0 {
		raw = req.Character
	}
	return parseCharacterJSON(raw)
}

func parseCharacterJSON(raw json.RawMessage) map[string]any {
	if len(raw) == 0 || string(raw) == "null" {
		return map[string]any{}
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		var m map[string]any
		if err := json.Unmarshal([]byte(s), &m); err == nil {
			return m
		}
		return map[string]any{}
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err == nil {
		return m
	}
	return map[string]any{}
}

func numField(m map[string]any, key string) float64 {
	switch v := m[key].(type) {
	case float64:
		return v
	case string:
		f, _ := strconv.ParseFloat(v, 64)
		return f
	}
	return 0
}

func strField(m map[string]any, key string) string {
	if s, ok := m[key].(string); ok {
		return s
	}
	return ""
}

func intField(m map[string]any, key string) int {
	return int(numField(m, key))
}

// intOrDefault mirrors Python's `int(x or default)`: a missing or falsy (0)
// value yields the default, so an explicit 0 is treated as "unset".
func intOrDefault(m map[string]any, key string, dflt int) int {
	v := intField(m, key)
	if v == 0 {
		return dflt
	}
	return v
}

// presentInt returns (value, true) only when the key actually exists, so
// "missing" (character_from_dict default applies) and "explicit 0" can be
// distinguished — Python's `data.get(key, default)` vs `int(x or fallback)`.
func presentInt(m map[string]any, key string) (int, bool) {
	v, ok := m[key]
	if !ok {
		return 0, false
	}
	switch t := v.(type) {
	case float64:
		return int(t), true
	case string:
		f, err := strconv.ParseFloat(t, 64)
		if err != nil {
			return 0, true
		}
		return int(f), true
	}
	return 0, true
}

// normalizedHealth mirrors the two-stage Python path: character_from_dict
// fills a default health of 70, then HealthCoachAgent reads `int(health or 50)`.
func normalizedHealth(c map[string]any) int {
	health := 70
	if v, ok := presentInt(c, "health"); ok {
		health = v
	}
	if health == 0 {
		health = 50
	}
	return health
}

// pyRound mirrors CPython round(x, ndigits): round-half-to-even.
func pyRound(x float64, ndigits int) float64 {
	p := math.Pow10(ndigits)
	f := x * p
	lower := math.Floor(f)
	frac := f - lower
	var result float64
	if frac < 0.5 {
		result = lower
	} else if frac > 0.5 {
		result = lower + 1
	} else if math.Mod(math.Abs(lower), 2) == 0 {
		result = lower
	} else {
		result = lower + 1
	}
	return result / p
}

// commaInt mirrors Python's f"{x:,.0f}" thousands separator formatting.
func commaInt(x float64) string {
	v := int64(pyRound(x, 0))
	s := strconv.FormatInt(v, 10)
	if v < 0 {
		return "-" + groupDigits(s[1:])
	}
	return groupDigits(s)
}

func groupDigits(s string) string {
	out := ""
	for i := 0; i < len(s); i++ {
		if i > 0 && (len(s)-i)%3 == 0 {
			out += ","
		}
		out += string(s[i])
	}
	return out
}

// strategies mirrors finance/portfolio.py STRATEGIES (the subset the advisors
// recommend: hyper_growth, balanced, recession_defense, dividend_income).
var strategies = map[string]map[string]any{
	"hyper_growth": {
		"name": "Hyper-Growth",
		"allocations": map[string]float64{
			"tech_stocks": 0.40, "leveraged_etf": 0.25, "crypto": 0.15,
			"emerging_markets": 0.10, "cash": 0.10,
		},
		"expected_return": 0.18, "volatility": 0.35, "sharpe_target": 2.1,
	},
	"balanced": {
		"name": "Balanced",
		"allocations": map[string]float64{
			"us_stocks": 0.30, "intl_stocks": 0.20, "bonds": 0.25,
			"real_estate": 0.15, "cash": 0.10,
		},
		"expected_return": 0.08, "volatility": 0.12, "sharpe_target": 1.0,
	},
	"recession_defense": {
		"name": "Recession Defense",
		"allocations": map[string]float64{
			"consumer_staples": 0.30, "gold": 0.25, "bonds": 0.25,
			"utilities": 0.10, "cash": 0.10,
		},
		"expected_return": 0.05, "volatility": 0.08, "sharpe_target": 1.4,
	},
	"dividend_income": {
		"name": "Dividend Aristocrats",
		"allocations": map[string]float64{
			"dividend_stocks": 0.40, "reits": 0.20, "bonds": 0.25,
			"preferred_stock": 0.10, "cash": 0.05,
		},
		"expected_return": 0.06, "volatility": 0.10, "sharpe_target": 0.8,
	},
}

// buildContinuity mirrors ai/advisor_dossier.py build_continuity.
func buildContinuity(characterData map[string]any, name string) map[string]any {
	prior := []string{}
	if raw, ok := characterData["prior_advice"].([]any); ok {
		for _, p := range raw {
			switch v := p.(type) {
			case string:
				if v != "" {
					prior = append(prior, v)
				}
			case float64:
				prior = append(prior, strconv.FormatFloat(v, 'f', -1, 64))
			}
		}
	}
	if len(prior) > 5 {
		prior = prior[:5]
	}
	summary := fmt.Sprintf("No prior advice on file for %s yet.", name)
	if len(prior) > 0 {
		label := "entries"
		if len(prior) == 1 {
			label = "entry"
		}
		summary = fmt.Sprintf("Building on %d prior advice %s for %s.", len(prior), label, name)
	}
	return map[string]any{
		"prior_advice_recalled": prior,
		"recalled_count":        len(prior),
		"summary":               summary,
	}
}

// ---------------------------------------------------------------------------
// Financial advisor (ai/financial_advisor.py deterministic core)
// ---------------------------------------------------------------------------

type FinState struct {
	NetWorth           float64
	LiquidCash         float64
	Debt               float64
	DebtToIncome       float64
	Portfolio          float64
	MonthlyIncome      float64
	EmergencyMonths    float64
	RiskProfile        string
	RecommendedStrategy string
}

func cmdAdvisorFinancial(req AdvisorRequest) {
	character := req.character()
	situation := firstNonEmpty(req.Situation, "general")
	writeJSON(map[string]any{
		"status":  "success",
		"backend": "go",
		"result":  financialAdvice(character, situation),
	})
}

func financialAdvice(c map[string]any, situation string) map[string]any {
	state := analyzeFinancialState(c)
	basic := map[string]any{
		"assessment":      financialAssessment(state),
		"recommendations": financialRecommendations(state, situation),
		"action_plan": map[string]any{
			"immediate": "Create a written budget; list all debts and expenses.",
			"30_days":   "Cut discretionary spending to raise the savings rate above 20%.",
			"90_days":   "Fund the emergency reserve to 3 months of expenses.",
			"6_months":  "Fully fund the 6-month emergency fund and start automated investing.",
			"long_term": "Rebalance quarterly and review the allocation once a year.",
		},
		"allocation":    allocationAdvice(state),
		"encouragement": financialEncouragement(state),
	}
	name := firstNonEmpty(strField(c, "name"), "Unknown")
	return map[string]any{
		"character_name":  name,
		"situation":       situation,
		"analysis":        financialStateMap(state),
		"assessment":      basic["assessment"],
		"recommendations": basic["recommendations"],
		"action_plan":     basic["action_plan"],
		"allocation":      basic["allocation"],
		"encouragement":   basic["encouragement"],
		"continuity":      buildContinuity(c, name),
	}
}

func analyzeFinancialState(c map[string]any) FinState {
	// Mirror character_from_dict + Character.__post_init__: `debt` is never
	// carried through character_from_dict, and net_worth is always recomputed
	// as money + portfolio_value, so the advisors observe debt=0 and the
	// recalculated net worth regardless of the input dict.
	money := numField(c, "money")
	portfolio := numField(c, "portfolio_value")
	netWorth := money + portfolio
	debt := 0.0
	income := estimateIncome(c)
	age := intField(c, "age")

	monthlyExpenses := income / 12 * 0.6
	if monthlyExpenses < 1 {
		monthlyExpenses = 1
	}
	emergencyFund := money
	if emergencyFund <= 0 {
		emergencyFund = math.Max(0, netWorth*0.1)
	}
	emergencyMonths := pyRound(emergencyFund/monthlyExpenses, 1)

	debtRatio := 0.0
	if income > 0 {
		debtRatio = pyRound(debt/income, 2)
	} else if debt > 0 {
		debtRatio = 1.0
	}

	riskProfile := riskProfile(age, netWorth, debtRatio)
	recommended := recommendedStrategy(age, netWorth)

	return FinState{
		NetWorth:            netWorth,
		LiquidCash:          money,
		Debt:                debt,
		DebtToIncome:        debtRatio,
		Portfolio:           portfolio,
		MonthlyIncome:       pyRound(income/12, 2),
		EmergencyMonths:     emergencyMonths,
		RiskProfile:         riskProfile,
		RecommendedStrategy: recommended,
	}
}

func financialStateMap(s FinState) map[string]any {
	return map[string]any{
		"net_worth":                 s.NetWorth,
		"liquid_cash":               s.LiquidCash,
		"debt":                      s.Debt,
		"debt_to_income_ratio":      s.DebtToIncome,
		"portfolio_value":           s.Portfolio,
		"estimated_monthly_income":  s.MonthlyIncome,
		"emergency_fund_months":     s.EmergencyMonths,
		"risk_profile":              s.RiskProfile,
		"recommended_strategy":      s.RecommendedStrategy,
	}
}

// estimateIncome mirrors FinancialAdvisorAgent._estimate_income (education base
// x occupation multiplier, matched in Python's dict insertion order).
func estimateIncome(c map[string]any) float64 {
	education := strField(c, "education_level")
	if education == "" {
		education = strField(c, "education")
	}
	if education == "" {
		education = "None" // character_from_dict default is "None"
	}
	base := 45000.0
	switch education {
	case "None":
		base = 25000
	case "Primary":
		base = 30000
	case "High School":
		base = 45000
	case "University":
		base = 70000
	}
	occupation := strings.ToLower(strField(c, "occupation"))
	multipliers := [][2]any{
		{"doctor", 5.0}, {"physician", 5.0}, {"surgeon", 6.0}, {"lawyer", 3.0},
		{"engineer", 2.0}, {"nurse", 1.6}, {"teacher", 1.2}, {"manager", 2.2},
		{"developer", 2.5}, {"financ", 2.5}, {"entrepreneur", 2.0}, {"executive", 4.0},
	}
	for _, entry := range multipliers {
		if strings.Contains(occupation, entry[0].(string)) {
			return base * entry[1].(float64)
		}
	}
	return base
}

func riskProfile(age int, netWorth, debtRatio float64) string {
	if debtRatio > 0.35 {
		return "conservative"
	}
	if age < 30 && netWorth >= 0 {
		return "aggressive"
	}
	if age < 50 {
		return "moderate"
	}
	return "conservative"
}

func recommendedStrategy(age int, netWorth float64) string {
	profile := riskProfile(age, netWorth, 0.0)
	if profile == "aggressive" {
		return "hyper_growth"
	}
	if profile == "conservative" {
		return "recession_defense"
	}
	if netWorth > 200000 {
		return "dividend_income"
	}
	return "balanced"
}

func financialAssessment(s FinState) string {
	nw := s.NetWorth
	if nw < 0 {
		return "Net worth is negative — the priority is eliminating debt and rebuilding a positive balance before investing."
	}
	if s.EmergencyMonths < 3 {
		return "Liquid savings cover less than 3 months of expenses — build the emergency fund before aggressive investing."
	}
	if nw >= 100000 {
		return "The financial foundation is solid; focus shifts to growth, tax efficiency, and long-term wealth preservation."
	}
	return "A reasonable starting point — the next step is consistent saving and a diversified allocation."
}

func financialRecommendations(s FinState, situation string) []string {
	recs := []string{}
	if s.Debt > 0 {
		recs = append(recs, fmt.Sprintf(
			"Pay off the %s debt aggressively (snowball or avalanche) — debt-to-income is %.2f.",
			commaInt(s.Debt), s.DebtToIncome))
	}
	if s.EmergencyMonths < 3 {
		recs = append(recs, fmt.Sprintf(
			"Build an emergency fund covering 6 months of expenses (currently %s month(s)).",
			strconv.FormatFloat(s.EmergencyMonths, 'f', 1, 64)))
	}
	if s.NetWorth >= 0 {
		recs = append(recs, fmt.Sprintf(
			"Automate saving at least 20%% of income into the %s allocation.",
			s.RecommendedStrategy))
	}
	if s.RiskProfile == "conservative" && s.NetWorth > 0 {
		recs = append(recs, "Prioritize capital preservation: bonds, dividend stocks, and gold over volatile assets.")
	}
	situationAdvice := map[string][]string{
		"general":        {"Review your budget monthly and track every peso for 30 days."},
		"debt_reduction": {"Negotiate interest rates with creditors and consolidate high-interest debt."},
		"investment":     {"Dollar-cost average monthly instead of timing the market; rebalance once a year."},
		"retirement":     {"Maximize tax-advantaged retirement accounts and let compounding run."},
		"buying_home":    {"Target a down payment of at least 20% to avoid mortgage insurance."},
		"emergency":      {"Liquidate volatile positions first; keep only essential expenses funded."},
	}
	adv, ok := situationAdvice[situation]
	if !ok {
		adv = situationAdvice["general"]
	}
	return append(recs, adv...)
}

func allocationAdvice(s FinState) map[string]any {
	info, ok := strategies[s.RecommendedStrategy]
	if !ok {
		info = strategies["balanced"]
	}
	return map[string]any{
		"strategy":        s.RecommendedStrategy,
		"name":            info["name"],
		"allocations":     info["allocations"],
		"expected_return": info["expected_return"],
		"volatility":      info["volatility"],
	}
}

func financialEncouragement(s FinState) string {
	if s.NetWorth < 0 {
		return "Debt is a chapter, not the whole book. Every payment moves the story forward."
	}
	if s.EmergencyMonths < 3 {
		return "Building the reserve first is the disciplined move — the markets will still be there."
	}
	return "Consistency beats brilliance. Keep the plan simple and show up every month."
}

// ---------------------------------------------------------------------------
// Health coach (ai/health_coach.py deterministic core)
// ---------------------------------------------------------------------------

type HealthState struct {
	HealthScore     int
	Happiness       int
	HealthCategory  string
	StressLevel     int
	RiskFactors     []string
	ExerciseRec     string
	SleepRec        string
}

func cmdAdvisorHealth(req AdvisorRequest) {
	character := req.character()
	situation := firstNonEmpty(req.Situation, "general")
	writeJSON(map[string]any{
		"status":  "success",
		"backend": "go",
		"result":  healthAdvice(character, situation),
	})
}

func healthAdvice(c map[string]any, situation string) map[string]any {
	state := analyzeHealthState(c)
	basic := map[string]any{
		"assessment":      healthAssessment(state),
		"recommendations": healthRecommendations(state, situation),
		"weekly_plan": map[string]any{
			"monday":    "30 min cardio + hydration focus",
			"tuesday":   "Strength session (full body, light weights)",
			"wednesday": "Active rest: walk and stretch 20 min",
			"thursday":  "30 min cardio + strength session",
			"friday":    "Flexibility: yoga or mobility routine",
			"saturday":  "Social activity or outdoor recreation",
			"sunday":    "Rest, meal prep, and sleep schedule reset",
		},
		"action_plan": map[string]any{
			"immediate": "Schedule 15 minutes of movement today; set a consistent wake time.",
			"30_days":   "Hit 150 minutes of weekly exercise and a fixed sleep window.",
			"90_days":   "Introduce two weekly strength sessions and a daily stress practice.",
			"6_months":  "Reassess health metrics; adjust the plan based on progress.",
			"long_term": "Build a sustainable routine that survives busy weeks.",
		},
		"encouragement": healthEncouragement(state),
	}
	name := firstNonEmpty(strField(c, "name"), "Unknown")
	return map[string]any{
		"character_name":  name,
		"situation":       situation,
		"analysis":        healthStateMap(state),
		"assessment":      basic["assessment"],
		"recommendations": basic["recommendations"],
		"weekly_plan":     basic["weekly_plan"],
		"action_plan":     basic["action_plan"],
		"encouragement":   basic["encouragement"],
		"continuity":      buildContinuity(c, name),
	}
}

func analyzeHealthState(c map[string]any) HealthState {
	health := normalizedHealth(c)
	happiness := intOrDefault(c, "happiness", 50)
	age := intField(c, "age")

	category := "poor"
	switch {
	case health >= 80:
		category = "excellent"
	case health >= 60:
		category = "good"
	case health >= 40:
		category = "fair"
	}

	risks := []string{}
	if health < 40 {
		risks = append(risks, "Chronic health risk — professional medical check-up recommended")
	}
	if happiness < 40 {
		risks = append(risks, "Low mood — stress and burnout are likely contributing factors")
	}
	if age > 50 && health < 60 {
		risks = append(risks, "Age-related decline — prioritize screening and strength training")
	}
	if happiness > 70 && health < 40 {
		risks = append(risks, "Happiness masking physical strain — do not ignore physical symptoms")
	}
	if len(risks) == 0 {
		risks = append(risks, "No major risk factors detected")
	}

	stress := 100 - int(math.Min(100, math.Max(0, float64(happiness+10))))

	exercise := "150+ minutes/week of moderate cardio plus two strength sessions"
	if age > 60 {
		exercise = "30 min daily of low-impact activity (walking, swimming, tai chi)"
	} else if health < 40 {
		exercise = "15 min daily walk first; build up gradually toward 30 min"
	}

	return HealthState{
		HealthScore:    health,
		Happiness:      happiness,
		HealthCategory: category,
		StressLevel:    stress,
		RiskFactors:    risks,
		ExerciseRec:    exercise,
		SleepRec:       "7-9",
	}
}

func healthStateMap(s HealthState) map[string]any {
	return map[string]any{
		"health_score":             s.HealthScore,
		"happiness_score":          s.Happiness,
		"health_category":          s.HealthCategory,
		"stress_level":             s.StressLevel,
		"risk_factors":             s.RiskFactors,
		"exercise_recommendation":  s.ExerciseRec,
		"sleep_recommendation":     s.SleepRec,
	}
}

func healthAssessment(s HealthState) string {
	switch s.HealthCategory {
	case "excellent":
		return "You are in excellent condition — the goal is maintenance, consistency, and prevention."
	case "good":
		return "Health is solid with clear room to improve fitness, sleep, and stress resilience."
	case "fair":
		return "Health needs active attention — small daily habits will compound into real gains."
	default:
		return "Health is fragile right now. Rest, medical guidance, and gentle movement come first."
	}
}

func healthRecommendations(s HealthState, situation string) []string {
	recs := []string{}
	if s.HealthScore < 40 {
		recs = append(recs, "See a healthcare professional before starting any intense program.")
	}
	recs = append(recs, "Aim for 7-9 hours of sleep and 8 glasses of water daily.")
	recs = append(recs, s.ExerciseRec)
	if s.StressLevel > 60 {
		recs = append(recs, "Incorporate a 10-minute daily mindfulness or breathing practice to lower stress.")
	}
	if s.Happiness < 50 {
		recs = append(recs, "Schedule weekly social time — connection is a measurable health input.")
	}
	situationAdvice := map[string][]string{
		"general":     {"Track sleep, steps, and mood for two weeks to find your baseline."},
		"weight_loss": {"Create a modest calorie deficit and add daily walking; avoid crash diets."},
		"fitness":     {"Progressively overload workouts — add small weight or reps each week."},
		"stress":      {"Set work boundaries, take real lunch breaks, and protect sleep as a non-negotiable."},
		"sleep":       {"Keep a fixed wake time, no screens an hour before bed, and a cool dark room."},
		"recovery":    {"Prioritize rest days and protein; sleep is where adaptation happens."},
	}
	adv, ok := situationAdvice[situation]
	if !ok {
		adv = situationAdvice["general"]
	}
	return append(recs, adv...)
}

func healthEncouragement(s HealthState) string {
	if s.HealthCategory == "poor" {
		return "Every journey starts with one kind, small step. Rest is productive too."
	}
	return "Health is built one ordinary day at a time — consistency quietly outperforms intensity."
}

// ---------------------------------------------------------------------------
// Mentor (ai/mentor.py deterministic core)
// ---------------------------------------------------------------------------

func cmdAdvisorMentor(req AdvisorRequest) {
	character := req.character()
	question := req.Question
	writeJSON(map[string]any{
		"status":  "success",
		"backend": "go",
		"result":  mentorship(character, question),
	})
}

func mentorship(c map[string]any, question string) map[string]any {
	name := firstNonEmpty(strField(c, "name"), "Unknown")
	financial := financialAdvice(c, "general")
	health := healthAdvice(c, "general")
	focus := focusAreas(c)
	basic := map[string]any{
		"assessment":      mentorAssessment(c),
		"focus_areas":     focus,
		"principles":      mentorPrinciples(),
		"action_plan":     mentorActionPlan(focus),
		"weekly_routine":  mentorWeeklyRoutine(),
		"mentor_response": mentorDefaultResponse(c, question),
	}
	return map[string]any{
		"character_name":   name,
		"question":         question,
		"assessment":       basic["assessment"],
		"focus_areas":      basic["focus_areas"],
		"principles":       basic["principles"],
		"action_plan":      basic["action_plan"],
		"weekly_routine":   basic["weekly_routine"],
		"mentor_response":  basic["mentor_response"],
		"financial_advisor": financial,
		"health_coach":     health,
		"life_coach":       baselineLifeAdvice(c),
		"continuity":       buildContinuity(c, name),
	}
}

func focusAreas(c map[string]any) []string {
	focus := []string{}
	if intOrDefault(c, "smarts", 50) < 60 {
		focus = append(focus, "Skills & Education")
	}
	if intOrDefault(c, "happiness", 50) < 55 {
		focus = append(focus, "Relationships & Fulfillment")
	}
	if intOrDefault(c, "health", 70) < 60 {
		focus = append(focus, "Health & Energy")
	}
	// Same recalculated net worth the Python Character exposes to the mentors
	// (money + portfolio_value; the raw net_worth input is overwritten).
	if numField(c, "money")+numField(c, "portfolio_value") < 20000 {
		focus = append(focus, "Financial Foundation")
	}
	if intOrDefault(c, "karma", 50) < 50 {
		focus = append(focus, "Integrity & Community")
	}
	if len(focus) == 0 {
		focus = append(focus, "Growth & Leverage")
	}
	return focus
}

func mentorAssessment(c map[string]any) string {
	age := intField(c, "age")
	if age < 25 {
		return "A defining window — choices about skills, habits, and people now compound for decades."
	}
	if age < 40 {
		return "The compounding years — career and relationships are being built while you still have energy to redirect."
	}
	if age < 60 {
		return "The leverage years — experience is your edge; delegate, mentor others, and protect your health."
	}
	return "The legacy years — focus on impact, mentorship, and financial security for the future."
}

func mentorPrinciples() []string {
	return []string{
		"Energy follows health: protect sleep and movement before everything else.",
		"Money is a tool, not a score — a quiet emergency fund buys more freedom than a loud splurge.",
		"Skills compound like investments: study the craft that pays your rent and opens doors.",
		"Relationships are the real net worth — invest in people who grow when you grow.",
		"Make the important small and the small important — daily habits beat heroic effort.",
	}
}

func mentorActionPlan(focus []string) map[string]any {
	plan := map[string]any{
		"immediate": "Choose one focus area and define a single concrete win for the week.",
		"30_days":   "Establish one new daily habit tied to that focus area.",
		"90_days":   "Finish one project or course that builds proof of skill.",
		"6_months":  "Revisit the focus areas; rebalance effort toward the weakest.",
		"long_term": "Define the person you are becoming and let goals serve that person.",
	}
	// Same fixed check order as MentorAgent._action_plan: financial first, then
	// health, so "Health & Energy" wins when both are present.
	for _, f := range focus {
		if f == "Financial Foundation" {
			plan["immediate"] = "Write a budget today; auto-save 20% before spending anything else."
		}
	}
	for _, f := range focus {
		if f == "Health & Energy" {
			plan["immediate"] = "Protect tonight's sleep and move for 15 minutes today."
		}
	}
	return plan
}

func mentorWeeklyRoutine() map[string]any {
	return map[string]any{
		"monday":    "Deep work on the top skill or project",
		"tuesday":   "Network: one conversation with someone ahead of you",
		"wednesday": "Health: strength or cardio session",
		"thursday":  "Financial review: track spending, save first",
		"friday":    "Reflect and plan the next week",
		"saturday":  "Relationships: quality time with key people",
		"sunday":    "Rest, read, and reset",
	}
}

func mentorDefaultResponse(c map[string]any, question string) string {
	name := firstNonEmpty(strField(c, "name"), "Unknown")
	focus := strings.Join(focusAreas(c), ", ")
	if strings.TrimSpace(question) == "" {
		return fmt.Sprintf(
			"%s, the highest-leverage moves right now are %s. Start with the smallest daily habit, then let momentum carry the rest.",
			name, focus)
	}
	return fmt.Sprintf(
		"On '%s': start with the honest version of your situation, choose one concrete step you can take this week, and treat the outcome as data, not verdict.",
		question)
}

// baselineLifeAdvice is the deterministic Go baseline for the life_coach block
// embedded in the mentor session (the full LifeCoachAgent stays Python-only;
// the Rust MCP client bridges to it for the real coaching output).
func baselineLifeAdvice(c map[string]any) map[string]any {
	name := firstNonEmpty(strField(c, "name"), "Unknown")
	return map[string]any{
		"character_name": name,
		"situation":      "general",
		"analysis": map[string]any{
			"overall_health": "baseline",
		},
		"specific_recommendations": []string{
			"Invest in health and learning consistently",
			"Build a diversified financial portfolio",
		},
		"recommendations": []string{
			"Invest in health and learning consistently",
			"Build a diversified financial portfolio",
		},
		"action_plan": map[string]any{
			"immediate_steps":  []string{"Sleep 7-9 hours", "Save 20% of income"},
			"short_term_goals": []string{"Build an emergency fund", "Learn a new skill"},
			"long_term_vision": "Create sustainable wealth and wellbeing",
		},
		"encouragement": "Keep building momentum — small consistent steps compound.",
		"message":       "baseline life coaching from Go core; use Rust client for full AI coaching",
	}
}

// reportDSNs converts the mysql:// URL into (full, base) go-sql-driver DSNs:
// full includes the database; base does not (used to CREATE DATABASE first).
func reportDSNs(urlDSN string) (full, base string) {
	rest := urlDSN
	if i := indexOf(urlDSN, "://"); i >= 0 {
		rest = urlDSN[i+3:]
	}
	creds := ""
	hostport := rest
	if i := indexOf(rest, "@"); i >= 0 {
		creds = rest[:i]
		hostport = rest[i+1:]
	}
	db := "alpha_zero"
	if i := indexOf(hostport, "/"); i >= 0 {
		hostport, db = hostport[:i], hostport[i+1:]
	}
	host := "127.0.0.1"
	port := "4000"
	if i := lastIndex(hostport, ":"); i >= 0 {
		host, port = hostport[:i], hostport[i+1:]
	}
	user := "root"
	password := ""
	if creds != "" {
		if i := indexOf(creds, ":"); i >= 0 {
			user, password = creds[:i], creds[i+1:]
		} else {
			user = creds
		}
	}
	common := fmt.Sprintf("%s:%s@tcp(%s:%s)", user, password, host, port)
	return common + "/" + db + "?timeout=3s&interpolateParams=true",
		common + "/?timeout=3s&interpolateParams=true"
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}

func lastIndex(s, sub string) int {
	for i := len(s) - len(sub); i >= 0; i-- {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}

func cmdReport(req ReportRequest) {
	urlDSN := req.DSN
	if urlDSN == "" {
		urlDSN = os.Getenv("ALPHA_ZERO_SQL_DSN")
	}
	if urlDSN == "" {
		urlDSN = "mysql://root@127.0.0.1:4000/alpha_zero"
	}
	full, base := reportDSNs(urlDSN)

	// Bootstrap the database idempotently (base DSN = no db selected yet).
	if req.Operation == "store" {
		raw, err := sql.Open("mysql", base)
		if err != nil {
			fail(fmt.Errorf("report: open base: %w", err))
		}
		raw.SetConnMaxLifetime(time.Minute)
		raw.SetMaxOpenConns(2)
		if _, err := raw.Exec("CREATE DATABASE IF NOT EXISTS alpha_zero"); err != nil {
			raw.Close()
			fail(fmt.Errorf("report: create db: %w", err))
		}
		raw.Close()
	}

	db, err := sql.Open("mysql", full)
	if err != nil {
		fail(fmt.Errorf("report: open: %w", err))
	}
	defer db.Close()
	db.SetConnMaxLifetime(time.Minute)
	db.SetMaxOpenConns(2)

	switch req.Operation {
	case "health":
		var one int
		if err := db.QueryRow("SELECT 1").Scan(&one); err != nil {
			writeJSON(map[string]any{"status": "error", "backend": "go", "healthy": false, "message": err.Error()})
			return
		}
		writeJSON(map[string]any{"status": "success", "backend": "go", "healthy": true})
	case "store":
		if req.ReportID == "" {
			fail(fmt.Errorf("report: store requires report_id"))
		}
		if _, err := db.Exec(reportSchema); err != nil {
			fail(fmt.Errorf("report: schema: %w", err))
		}
		config, err := json.Marshal(req.Config)
		if err != nil {
			fail(fmt.Errorf("report: config: %w", err))
		}
		report, err := json.Marshal(req.Report)
		if err != nil {
			fail(fmt.Errorf("report: report: %w", err))
		}
		backend := req.Backend
		if backend == "" {
			backend = "go"
		}
		runType := req.RunType
		if runType == "" {
			runType = "multiverse"
		}
		_, err = db.Exec(`INSERT INTO simulation_reports (id, run_type, config, report, backend)
			VALUES (?, ?, ?, ?, ?)
			ON DUPLICATE KEY UPDATE run_type = VALUES(run_type), report = VALUES(report), backend = VALUES(backend)`,
			req.ReportID, runType, string(config), string(report), backend)
		if err != nil {
			fail(fmt.Errorf("report: store: %w", err))
		}
		writeJSON(map[string]any{"status": "success", "backend": "go", "stored": true, "report_id": req.ReportID})
	case "load":
		if req.ReportID == "" {
			fail(fmt.Errorf("report: load requires report_id"))
		}
		var reportJSON []byte
		if err := db.QueryRow("SELECT report FROM simulation_reports WHERE id = ?", req.ReportID).Scan(&reportJSON); err != nil {
			if err == sql.ErrNoRows {
				writeJSON(map[string]any{"status": "success", "backend": "go", "found": false})
				return
			}
			fail(fmt.Errorf("report: load: %w", err))
		}
		var payload any
		if err := json.Unmarshal(reportJSON, &payload); err != nil {
			fail(fmt.Errorf("report: decode: %w", err))
		}
		writeJSON(map[string]any{"status": "success", "backend": "go", "found": true, "report": payload})
	case "list":
		limit := req.Limit
		if limit <= 0 {
			limit = 50
		}
		rows, err := db.Query(`SELECT id, run_type, backend, created_at FROM simulation_reports
			ORDER BY created_at DESC LIMIT ?`, limit)
		if err != nil {
			fail(fmt.Errorf("report: list: %w", err))
		}
		defer rows.Close()
		items := []map[string]any{}
		for rows.Next() {
			var id, runType, backend string
			var createdAt []byte
			if err := rows.Scan(&id, &runType, &backend, &createdAt); err != nil {
				fail(fmt.Errorf("report: list scan: %w", err))
			}
			ts := ""
			if len(createdAt) > 0 {
				ts = string(createdAt)
			}
			items = append(items, map[string]any{
				"id": id, "run_type": runType, "backend": backend,
				"created_at": ts,
			})
		}
		if err := rows.Err(); err != nil {
			fail(fmt.Errorf("report: list: %w", err))
		}
		writeJSON(map[string]any{"status": "success", "backend": "go", "results": items, "count": len(items)})
	default:
		fail(fmt.Errorf("report: unknown operation %q", req.Operation))
	}
}

func str(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
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
	case "interview":
		var req InterviewRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdInterview(req)
	case "coach":
		var req CoachingRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdCoach(req)
	case "analyze":
		var req AnalyzeRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdAnalyze(req)
	case "narrate":
		var req NarrateRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdNarrate(req)
	case "memory":
		var req MemoryRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdMemory(req)
	case "report":
		var req ReportRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdReport(req)
	case "advisor_financial":
		var req AdvisorRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdAdvisorFinancial(req)
	case "advisor_health":
		var req AdvisorRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdAdvisorHealth(req)
	case "advisor_mentor":
		var req AdvisorRequest
		if err := json.Unmarshal(raw, &req); err != nil {
			fail(err)
		}
		cmdAdvisorMentor(req)
	default:
		writeJSON(map[string]any{"error": "unknown command: " + cmd})
		os.Exit(1)
	}
}
