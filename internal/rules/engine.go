package rules

import (
	"fmt"
	"io/ioutil"
	"os"
	"regexp"
	"strings"
	"sync"
)

// Rule represents a single routing rule
type Rule struct {
	Type    string // "exact", "glob", "regex"
	Pattern string
	Action  string // "always_route", "do_not_route"
}

// RuleEngine manages routing rules
type RuleEngine struct {
	mu          sync.RWMutex
	alwaysRoute []Rule
	doNotRoute  []Rule
	exactCache  map[string]string // domain → action (for fast exact lookups)
}

// NewRuleEngine creates a new rule engine
func NewRuleEngine() *RuleEngine {
	return &RuleEngine{
		alwaysRoute: []Rule{},
		doNotRoute:  []Rule{},
		exactCache:  make(map[string]string),
	}
}

// AddRule adds a new routing rule
func (re *RuleEngine) AddRule(ruleType, pattern, action string) error {
	re.mu.Lock()
	defer re.mu.Unlock()

	// Normalize inputs
	ruleType = strings.ToLower(strings.TrimSpace(ruleType))
	pattern = strings.ToLower(strings.TrimSpace(pattern))
	action = strings.ToLower(strings.TrimSpace(action))

	if pattern == "" {
		return fmt.Errorf("pattern cannot be empty")
	}

	if action != "always_route" && action != "do_not_route" {
		return fmt.Errorf("invalid action: %s", action)
	}

	if ruleType == "" {
		// Auto-detect type
		if strings.Contains(pattern, "*") || strings.Contains(pattern, "?") {
			ruleType = "glob"
		} else if strings.HasPrefix(pattern, "re:") {
			ruleType = "regex"
			pattern = pattern[3:] // remove "re:" prefix
		} else {
			ruleType = "exact"
		}
	}

	// Validate regex if needed
	if ruleType == "regex" {
		if _, err := regexp.Compile(pattern); err != nil {
			return fmt.Errorf("invalid regex: %v", err)
		}
	}

	rule := Rule{
		Type:    ruleType,
		Pattern: pattern,
		Action:  action,
	}

	if action == "always_route" {
		re.alwaysRoute = append(re.alwaysRoute, rule)
		if ruleType == "exact" {
			re.exactCache[pattern] = "always"
		}
	} else {
		re.doNotRoute = append(re.doNotRoute, rule)
		if ruleType == "exact" {
			re.exactCache[pattern] = "do_not"
		}
	}

	return nil
}

// Match checks if a domain matches any rule
// Returns (matched, action) where matched is true if rule found
func (re *RuleEngine) Match(domain string) (bool, string) {
	re.mu.RLock()
	defer re.mu.RUnlock()

	domain = strings.ToLower(strings.TrimSpace(domain))
	domain = strings.TrimPrefix(domain, ".")

	// Check exact cache first
	if action, ok := re.exactCache[domain]; ok {
		return true, action
	}

	// Check alwaysRoute
	if action := re.matchRules(domain, re.alwaysRoute); action != "" {
		return true, action
	}

	// Check doNotRoute
	if action := re.matchRules(domain, re.doNotRoute); action != "" {
		return true, action
	}

	return false, ""
}

// matchRules checks if domain matches any rule in the list
func (re *RuleEngine) matchRules(domain string, rules []Rule) string {
	for _, rule := range rules {
		if re.ruleMatches(domain, rule) {
			return rule.Action
		}
	}
	return ""
}

// ruleMatches checks if a domain matches a single rule
func (re *RuleEngine) ruleMatches(domain string, rule Rule) bool {
	switch rule.Type {
	case "exact":
		return domain == rule.Pattern || domain == "."+rule.Pattern ||
			strings.HasSuffix(domain, "."+rule.Pattern)

	case "glob":
		// Simple glob implementation
		return re.globMatch(domain, rule.Pattern)

	case "regex":
		re, err := regexp.Compile(rule.Pattern)
		if err != nil {
			return false
		}
		return re.MatchString(domain)
	}

	return false
}

// globMatch implements basic glob pattern matching
func (re *RuleEngine) globMatch(name, pattern string) bool {
	runes := make([]rune, len(name))
	for i, r := range name {
		runes[i] = r
	}
	pRunes := make([]rune, len(pattern))
	for i, r := range pattern {
		pRunes[i] = r
	}

	return globMatchRec(runes, pRunes)
}

// globMatchRec recursively matches glob patterns
func globMatchRec(s, p []rune) bool {
	for len(p) > 0 {
		switch p[0] {
		case '?':
			if len(s) == 0 {
				return false
			}
			s = s[1:]
			p = p[1:]

		case '*':
			if len(p) == 1 {
				return true
			}
			if globMatchRec(s, p[1:]) {
				return true
			}
			if len(s) > 0 {
				s = s[1:]
				continue
			}
			return false

		default:
			if len(s) == 0 || s[0] != p[0] {
				return false
			}
			s = s[1:]
			p = p[1:]
		}
	}
	return len(s) == 0
}

// GetAllRules returns all rules
func (re *RuleEngine) GetAllRules() (always, doNot []Rule) {
	re.mu.RLock()
	defer re.mu.RUnlock()

	alwaysCopy := make([]Rule, len(re.alwaysRoute))
	copy(alwaysCopy, re.alwaysRoute)

	doNotCopy := make([]Rule, len(re.doNotRoute))
	copy(doNotCopy, re.doNotRoute)

	return alwaysCopy, doNotCopy
}

// ClearRules removes all rules
func (re *RuleEngine) ClearRules() {
	re.mu.Lock()
	defer re.mu.Unlock()

	re.alwaysRoute = []Rule{}
	re.doNotRoute = []Rule{}
	re.exactCache = make(map[string]string)
}

// SaveToFile saves rules to a file
func (re *RuleEngine) SaveToFile(filepath string) error {
	re.mu.RLock()
	defer re.mu.RUnlock()

	var lines []string
	for _, rule := range re.alwaysRoute {
		lines = append(lines, fmt.Sprintf("always_route:%s:%s:%s", rule.Type, rule.Pattern, rule.Action))
	}
	for _, rule := range re.doNotRoute {
		lines = append(lines, fmt.Sprintf("do_not_route:%s:%s:%s", rule.Type, rule.Pattern, rule.Action))
	}

	content := strings.Join(lines, "\n")
	if content != "" {
		content += "\n"
	}

	return os.WriteFile(filepath, []byte(content), 0o644)
}

// LoadFromFile loads rules from a file
func (re *RuleEngine) LoadFromFile(filepath string) error {
	data, err := ioutil.ReadFile(filepath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}

	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		parts := strings.Split(line, ":")
		if len(parts) < 4 {
			continue
		}

		action := parts[0]
		ruleType := parts[1]
		pattern := strings.Join(parts[2:], ":")

		re.AddRule(ruleType, pattern, action)
	}

	return nil
}
