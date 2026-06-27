package scanner

import (
	"sync/atomic"
	"time"
)

// waitWhilePaused blocks new probe work while Pause is active. It returns false
// if Stop is requested while waiting.
func (s *Scanner) waitWhilePaused() bool {
	if s == nil {
		return true
	}
	for atomic.LoadInt32(&s.paused) == 1 {
		if atomic.LoadInt32(&s.stopped) == 1 {
			return false
		}
		time.Sleep(100 * time.Millisecond)
	}
	return atomic.LoadInt32(&s.stopped) == 0
}
