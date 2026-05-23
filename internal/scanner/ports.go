package scanner

// SetTargetPorts updates the scanner's active target ports.
func (s *Scanner) SetTargetPorts(ports []int) {
	if s == nil || s.config == nil {
		return
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	s.config.TargetPorts = append([]int(nil), ports...)
}

// GetTargetPorts returns a copy of the scanner's current target ports.
func (s *Scanner) GetTargetPorts() []int {
	if s == nil || s.config == nil {
		return nil
	}

	s.mu.RLock()
	defer s.mu.RUnlock()

	return append([]int(nil), s.config.TargetPorts...)
}
