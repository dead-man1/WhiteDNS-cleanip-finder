# WhiteDNS — Go Port (Updated)

This repository contains the Go port of the WhiteDNS project. This README has been updated to reflect the current state: the scanner subsystem has been fully ported to Go, cross-platform builds are available, and core CLI/UI flows are functional.

## Status (May 2026)

- Project: Go port of WhiteDNS — active.
- Scanner: Fully ported to Go (native workers, CIDR expansion, port scanning, adaptive throttling, and export features).
- TUI: Core menu and UI flows implemented in Go (`internal/ui`) and tested.
- Bridge: Python bridge remains for select legacy tooling where native parity is not yet required.
- Build: Cross-platform build script produces Windows, Linux (amd64/arm64), and Termux/Android artifacts.

## Implemented (high level)

- Networking primitives: TCP proxy, HTTP CONNECT tunneling, SOCKS5 support.
- Scanner: Complete Go scanner pipeline including:
  - CIDR parsing and expansion
  - Parallel scanning workers with adaptive throttling
  - Port probing, banner grab, and result export
  - ASN-aware target handling
  - Export and CSV assets under `builds/` for distribution
- CLI/TUI: Interactive terminal UI using `internal/ui` with menu, scan controls, and logs.
- Router/Proxy: Basic route/persistence plumbing and proxy server implementation.

## Not yet ported / future work

- MMDF/TLS MITM CA lifecycle (partial)
- DPI engine (experimental features)
- Some advanced Python-only tooling remains behind the bridge and can be ported on demand.

## Quickstart — development

Prerequisites: Go (1.20+ recommended), PowerShell (Windows), or bash (Linux/macOS).

Run the TUI:

```powershell
cd go-port
go run ./cmd/whitedns -mode ui -host 0.0.0.0 -port 7080
```

Run proxy-only mode:

```powershell
cd go-port
go run ./cmd/whitedns -mode proxy -host 0.0.0.0 -port 7080
```

Run the test/compile check:

```powershell
cd go-port
go test ./...
```

## Cross-platform builds

The repository includes `build_cross_platform.ps1` which produces binaries for multiple targets into the `builds/` folder.

To reproduce locally (PowerShell):

```powershell
cd go-port
./build_cross_platform.ps1
```

Generated artifacts (local run):

- `builds/whitedns-windows-amd64.exe`
- `builds/whitedns-linux-amd64`
- `builds/whitedns-linux-arm64`
- `builds/whitedns-macos-amd64`
- `builds/whitedns-macos-arm64`
- `builds/whitedns-termux-arm64`

The `builds/` directory also includes required data files copied during the build (e.g., `IranASNs/`, `assets/`).

