# WhiteDNS Go Port (Phase 1)

This is an incremental Go port scaffold that keeps the original Python project untouched.

It now includes a Go CLI UI compatibility mode that mirrors the Python main menu and delegates scanner/menu actions to Python cores through a bridge script.

## Implemented in Phase 1

- TCP proxy server
- HTTP proxy handling
- HTTPS `CONNECT` tunneling
- SOCKS5 `CONNECT` (no-auth)
- Bidirectional stream relay
- Go CLI menu shell with White/Desync modes (mirrors current Python menu)
- Python bridge actions for scanner and tooling parity from the Go UI
- Config via env vars:
  - `WHITE_PROXY_HOST` (default: `0.0.0.0`)
  - `WHITE_PROXY_PORT` (default: `7080`)
  - `WHITE_PROXY_PYTHON` (optional Python executable override for bridge)

## Not yet ported (native Go parity)

- MMDF / TLS MITM CA lifecycle
- DPI desync engine and raw socket injection
- Route manager, scanner, ASN tooling, and UI menus
- Domain-specific race and route persistence

The bridge mode calls Python for those actions today so scanner behavior remains available from the Go UI.

## Run

```powershell
cd go-port
go run ./cmd/whitedns -mode ui -host 0.0.0.0 -port 7080
```

Direct proxy mode only:

```powershell
cd go-port
go run ./cmd/whitedns -mode proxy -host 0.0.0.0 -port 7080
```

## Build

```powershell
cd go-port
go build -o whitedns-go.exe ./cmd/whitedns
```

## Migration Strategy

Phase 2 ports route/cache logic from Python `utils/route_manager.py`.
Phase 3 ports scanner workers and preflight integrations.
Phase 4 ports MMDF and optional DPI paths.
