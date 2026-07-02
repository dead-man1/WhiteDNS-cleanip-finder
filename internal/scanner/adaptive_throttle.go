package scanner

import (
	"sync"
	"sync/atomic"
	"time"
)

// AdaptiveThrottle dynamically adjusts concurrency based on timeout rates
// Inspired by Python's cores/adaptive_throttle.py
type AdaptiveThrottle struct {
	// These two are accessed with 64-bit atomics (atomic.AddInt64 etc). On 32-bit
	// platforms (e.g. armv7/GOARCH=arm) a 64-bit atomic operand MUST be 8-byte
	// aligned or the program panics with "unaligned 64-bit atomic operation".
	// Go only guarantees 64-bit alignment for the *first word* of an allocated
	// struct, so these MUST stay at the very top — do not move them below the
	// int32 fields, which would push them to a 4-byte-aligned offset and crash
	// the scan on 32-bit devices. See https://pkg.go.dev/sync/atomic#pkg-note-BUG
	timeouts  int64
	successes int64

	mu           sync.RWMutex
	currentLimit int32
	maxLimit     int32
	minLimit     int32
	// Use a larger sample window to avoid reacting to short, scan-local
	// bursts of timeouts caused by large numbers of dead IPs.
	windowSize         int
	lastAdjustmentTime time.Time
	targetTimeoutRate  float64 // e.g., 0.05 = 5% acceptable timeout rate
	logf               func(string, ...interface{})
}

// NewAdaptiveThrottle creates a new throttle with initial concurrency
func NewAdaptiveThrottle(initialLimit, minLimit, maxLimit int, targetTimeoutRate float64, logfn func(string, ...interface{})) *AdaptiveThrottle {
	return &AdaptiveThrottle{
		currentLimit:      int32(initialLimit),
		maxLimit:          int32(maxLimit),
		minLimit:          int32(minLimit),
		targetTimeoutRate: targetTimeoutRate,
		// larger window to reduce sensitivity to short bursts of dead IPs
		windowSize:         200,
		lastAdjustmentTime: time.Now(),
		logf:               logfn,
	}
}

// RecordSuccess records a successful probe
func (at *AdaptiveThrottle) RecordSuccess() {
	atomic.AddInt64(&at.successes, 1)
	at.maybeAdjust()
}

// RecordTimeout records a timeout/failure
func (at *AdaptiveThrottle) RecordTimeout() {
	atomic.AddInt64(&at.timeouts, 1)
	at.maybeAdjust()
}

// maybeAdjust checks if we should adjust concurrency based on recent performance
func (at *AdaptiveThrottle) maybeAdjust() {
	at.mu.Lock()
	defer at.mu.Unlock()

	now := time.Now()
	if now.Sub(at.lastAdjustmentTime) < 3*time.Second {
		return // Only adjust every 3 seconds
	}

	successes := atomic.LoadInt64(&at.successes)
	timeouts := atomic.LoadInt64(&at.timeouts)
	total := successes + timeouts

	if total < int64(at.windowSize) {
		return // Not enough samples yet
	}

	timeoutRate := float64(timeouts) / float64(total)
	currentLimit := atomic.LoadInt32(&at.currentLimit)

	// Be conservative: require a larger deviation before dropping, and back
	// off more gently so scans don't thrash. Likewise grow slowly.
	if timeoutRate > at.targetTimeoutRate*2.0 {
		// Significant timeout burst — reduce concurrency moderately.
		newLimit := int32(float64(currentLimit) * 0.88)
		if newLimit < at.minLimit {
			newLimit = at.minLimit
		}
		atomic.StoreInt32(&at.currentLimit, newLimit)
		at.logf("[ADAPTIVE] Reducing concurrency: %d → %d (timeout rate: %.1f%%)\n", currentLimit, newLimit, timeoutRate*100)
	} else if timeoutRate < at.targetTimeoutRate*0.5 && currentLimit < at.maxLimit {
		// Low timeout rate, can increase concurrency more quickly
		newLimit := int32(float64(currentLimit) * 1.15)
		if newLimit > at.maxLimit {
			newLimit = at.maxLimit
		}
		atomic.StoreInt32(&at.currentLimit, newLimit)
		at.logf("[ADAPTIVE] Increasing concurrency: %d → %d (timeout rate: %.1f%%)\n", currentLimit, newLimit, timeoutRate*100)
	}

	// Reset counters
	atomic.StoreInt64(&at.successes, 0)
	atomic.StoreInt64(&at.timeouts, 0)
	at.lastAdjustmentTime = now
}

// CurrentLimit returns the current concurrency limit
func (at *AdaptiveThrottle) CurrentLimit() int {
	return int(atomic.LoadInt32(&at.currentLimit))
}

// SetLimit forcibly sets the concurrency limit
func (at *AdaptiveThrottle) SetLimit(limit int) {
	if limit < int(at.minLimit) {
		limit = int(at.minLimit)
	}
	if limit > int(at.maxLimit) {
		limit = int(at.maxLimit)
	}
	atomic.StoreInt32(&at.currentLimit, int32(limit))
}

// GetTimeoutRate returns the current timeout rate (timeouts / total)
func (at *AdaptiveThrottle) GetTimeoutRate() float64 {
	successes := atomic.LoadInt64(&at.successes)
	timeouts := atomic.LoadInt64(&at.timeouts)
	total := successes + timeouts
	if total == 0 {
		return 0.0
	}
	return float64(timeouts) / float64(total)
}
