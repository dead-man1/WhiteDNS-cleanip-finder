package bridge

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

type PythonBridge struct {
	ProjectRoot string
	GoPortRoot  string
	PythonBin   string
}

func New(projectRoot, goPortRoot string) *PythonBridge {
	return &PythonBridge{
		ProjectRoot: projectRoot,
		GoPortRoot:  goPortRoot,
		PythonBin:   detectPython(projectRoot, goPortRoot),
	}
}

func (b *PythonBridge) RunAction(action string) error {
	bridgeScript := filepath.Join(b.GoPortRoot, "python_bridge.py")
	cmd := exec.Command(b.PythonBin, bridgeScript, "--action", action)
	cmd.Dir = b.ProjectRoot
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = os.Environ()
	return cmd.Run()
}

func detectPython(projectRoot, goPortRoot string) string {
	if env := os.Getenv("WHITE_PROXY_PYTHON"); env != "" {
		return env
	}

	if isWindows() {
		bundledPy := filepath.Join(goPortRoot, ".venv", "Scripts", "python.exe")
		if fileExists(bundledPy) {
			return bundledPy
		}
	}

	if !isWindows() {
		bundledPy := filepath.Join(goPortRoot, ".venv", "bin", "python")
		if fileExists(bundledPy) {
			return bundledPy
		}
	}

	if isWindows() {
		venvPy := filepath.Join(projectRoot, ".venv", "Scripts", "python.exe")
		if fileExists(venvPy) {
			return venvPy
		}
		return "python"
	}

	venvPy := filepath.Join(projectRoot, ".venv", "bin", "python")
	if fileExists(venvPy) {
		return venvPy
	}
	return "python3"
}

func fileExists(path string) bool {
	st, err := os.Stat(path)
	return err == nil && !st.IsDir()
}

func isWindows() bool {
	return os.PathSeparator == '\\'
}

func (b *PythonBridge) String() string {
	return fmt.Sprintf("PythonBridge{python=%s}", b.PythonBin)
}
