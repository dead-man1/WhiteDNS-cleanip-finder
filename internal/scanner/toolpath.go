package scanner

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

// ResolveToolPath returns the best available executable path for an external scanner tool.
// Search order:
// 1. Explicit env var override (WHITE_PROXY_MASSCAN / WHITE_PROXY_NMAP)
// 2. Local bundle folders next to the executable: tools/, bin/, and the executable dir
// 3. The system PATH via exec.LookPath
func ResolveToolPath(name string) (string, error) {
	if envName := toolEnvName(name); envName != "" {
		if envPath := os.Getenv(envName); envPath != "" {
			if fileExists(envPath) {
				return envPath, nil
			}
			return "", fmt.Errorf("%s points to a missing executable: %s", envName, envPath)
		}
	}

	for _, candidate := range toolCandidates(name) {
		if fileExists(candidate) {
			return candidate, nil
		}
	}

	if path, err := exec.LookPath(name); err == nil {
		return path, nil
	}

	return "", fmt.Errorf("%s executable not found on PATH or in bundled tool folders", name)
}

// ToolAvailable reports whether an external tool can be resolved.
func ToolAvailable(name string) bool {
	_, err := ResolveToolPath(name)
	return err == nil
}

func toolEnvName(name string) string {
	switch name {
	case "masscan":
		return "WHITE_PROXY_MASSCAN"
	case "nmap":
		return "WHITE_PROXY_NMAP"
	default:
		return ""
	}
}

func toolCandidates(name string) []string {
	var names []string
	baseDir, _ := os.Executable()
	if baseDir != "" {
		baseDir = filepath.Dir(baseDir)
	}

	rootCandidates := []string{}
	if wd, err := os.Getwd(); err == nil {
		rootCandidates = append(rootCandidates, wd)
	}
	if baseDir != "" {
		rootCandidates = append(rootCandidates, baseDir)
	}

	toolNames := []string{name}
	if runtime.GOOS == "windows" {
		toolNames = append(toolNames, name+".exe")
	}

	for _, root := range rootCandidates {
		for _, subdir := range []string{"tools", "bin", ""} {
			for _, toolName := range toolNames {
				if subdir == "" {
					names = append(names, filepath.Join(root, toolName))
				} else {
					names = append(names, filepath.Join(root, subdir, toolName))
				}
			}
		}
	}

	return names
}

func fileExists(path string) bool {
	st, err := os.Stat(path)
	return err == nil && !st.IsDir()
}
