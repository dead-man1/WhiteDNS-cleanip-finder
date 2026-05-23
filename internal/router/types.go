package router

import (
	"sync"
	"time"
)

// RouteEntry represents a cached route to an endpoint
type RouteEntry struct {
	Endpoint   string
	LatencyMs  float64
	LastUsed   time.Time
	Score      float64
	IsVerified bool
	Domain     string
}

// DomainCache holds L1 (active) and L2 (history) routes
type DomainCache struct {
	mu           sync.RWMutex
	Primary      []RouteEntry         // L1: hot endpoints tried first
	Secondary    []RouteEntry         // L2: fallback endpoints
	History      map[string]time.Time // recently failed
	ExpiryTime   time.Duration
	LastRaceTime time.Time
}

// Router manages domain-to-endpoint routing with race selection
type Router struct {
	mu             sync.RWMutex
	domainCaches   map[string]*DomainCache
	endpointStats  map[string]*EndpointStats
	raceInProgress map[string]bool
	raceSem        chan struct{} // concurrency limit
	config         *RouterConfig
	sessionMetrics *SessionMetrics
	routeFilePath  string // persistence file path
}

// RouterConfig holds router tuning
type RouterConfig struct {
	L1CacheTTLMs           int
	L2CacheTTLMs           int
	HistoryTTLSec          int
	RaceMaxConcurrency     int
	RaceTimeoutMs          int
	FailureQuarantineSec   float64
	MaxPrimaryCandidates   int
	MaxSecondaryCandidates int
}

// EndpointStats tracks per-endpoint health
type EndpointStats struct {
	mu                  sync.RWMutex
	SuccessCount        int
	FailCount           int
	AvgLatencyMs        float64
	ConsecutiveFailures int
	LastSuccessTime     time.Time
	LastFailTime        time.Time
	QuarantineUntil     time.Time
	QuarantineReason    string
}

// SessionMetrics tracks routing session statistics
type SessionMetrics struct {
	mu                  sync.RWMutex
	StartTime           time.Time
	TotalRequests       int
	HotStarts           int
	ColdStarts          int
	L1Hits              int
	L2Hits              int
	RacesStarted        int
	RaceWins            int
	RaceFailures        int
	RaceTimesMs         []float64
	SelectedLatenciesMs []float64
	Reroutes            int
	RerouteTimesMs      []float64
}

// RaceCandidate represents an endpoint competing in a race
type RaceCandidate struct {
	Endpoint   string
	LatencyMs  float64
	WinTime    time.Time
	WinLatency time.Duration
}

// MatchRule represents a domain matching pattern
type MatchRule struct {
	Type    string // "exact", "glob", "regex"
	Pattern string
	Action  string // "always_route", "do_not_route"
}
