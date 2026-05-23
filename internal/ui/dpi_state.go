package ui

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type dpiState struct {
	ConnectionMode    string   `json:"connection_mode"`
	DpiSNI            string   `json:"dpi_sni"`
	DpiIP             string   `json:"dpi_ip"`
	MmdfSNI           string   `json:"mmdf_sni"`
	MmdfIP            string   `json:"mmdf_ip"`
	DpiStrategies     []string `json:"dpi_strategies"`
	ActiveDpiStrategy string   `json:"active_dpi_strategy"`
	DpiFragmentation  bool     `json:"dpi_fragmentation"`
	AlwaysShowDpiLogs bool     `json:"always_show_dpi_logs"`
}

func defaultDPIState() dpiState {
	return dpiState{
		ConnectionMode:    "white_ip",
		DpiSNI:            "speed.cloudflare.com",
		DpiIP:             "",
		MmdfSNI:           "",
		MmdfIP:            "",
		DpiStrategies:     []string{"oob"},
		ActiveDpiStrategy: "oob",
		DpiFragmentation:  true,
		AlwaysShowDpiLogs: false,
	}
}

func dpiStatePath(dataDir string) string {
	return filepath.Join(dataDir, "dpi_config.json")
}

func loadDPIState(dataDir string) dpiState {
	state := defaultDPIState()
	path := dpiStatePath(dataDir)
	data, err := os.ReadFile(path)
	if err != nil {
		return state
	}
	_ = json.Unmarshal(data, &state)
	state.normalize()
	return state
}

func saveDPIState(dataDir string, state dpiState) error {
	state.normalize()
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		return err
	}
	return os.WriteFile(dpiStatePath(dataDir), data, 0o644)
}

func (s *dpiState) normalize() {
	if strings.TrimSpace(s.DpiSNI) == "" {
		s.DpiSNI = "speed.cloudflare.com"
	}
	if len(s.DpiStrategies) == 0 {
		s.DpiStrategies = []string{"oob"}
	}
	seen := make(map[string]struct{})
	filtered := make([]string, 0, len(s.DpiStrategies))
	valid := map[string]struct{}{"oob": {}, "bad_csum": {}, "ttl": {}, "syn": {}, "rst": {}, "fin": {}, "classic": {}}
	for _, strat := range s.DpiStrategies {
		strat = strings.TrimSpace(strings.ToLower(strat))
		if strat == "" {
			continue
		}
		if _, ok := valid[strat]; !ok {
			continue
		}
		if _, ok := seen[strat]; ok {
			continue
		}
		seen[strat] = struct{}{}
		filtered = append(filtered, strat)
	}
	if len(filtered) == 0 {
		filtered = []string{"oob"}
	}
	s.DpiStrategies = filtered
	if s.ActiveDpiStrategy == "" || !containsString(s.DpiStrategies, s.ActiveDpiStrategy) {
		s.ActiveDpiStrategy = s.DpiStrategies[0]
	}
}

func containsString(items []string, needle string) bool {
	for _, item := range items {
		if item == needle {
			return true
		}
	}
	return false
}

func sortedDPIMapKeys(values map[string][]string) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func joinLines(values []string) string {
	if len(values) == 0 {
		return ""
	}
	return strings.Join(values, "\n") + "\n"
}

func formatDPIStateSummary(state dpiState) string {
	return fmt.Sprintf("mode=%s sni=%s ip=%s strategies=%v frag=%v logs=%v",
		state.ConnectionMode, state.DpiSNI, state.DpiIP, state.DpiStrategies, state.DpiFragmentation, state.AlwaysShowDpiLogs)
}
