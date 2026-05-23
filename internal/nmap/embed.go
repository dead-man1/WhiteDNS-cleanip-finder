package nmap

import "fmt"

// GetNmapBinary is kept for compatibility when a bundled binary is added later.
// The current build does not require an embedded nmap executable.
func GetNmapBinary() ([]byte, error) {
	return nil, fmt.Errorf("bundled nmap binary is not available in this build")
}
