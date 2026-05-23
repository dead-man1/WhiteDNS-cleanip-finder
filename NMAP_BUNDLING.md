# Bundling nmap into whitedns.exe

## Overview

This document explains how to bundle nmap directly into the whitedns executable so it's always available as an option without requiring a separate installation.

## Prerequisites

- Go 1.16+ (for `embed` package support)
- nmap executable (for Windows)

## Step-by-step Setup

### 1. Obtain nmap.exe

Download nmap for Windows from the official source:
- **Official**: https://nmap.org/download.html
- **Alternative**: Install from chocolatey: `choco install nmap`

You need the `nmap.exe` binary.

### 2. Create the embedding directory

```bash
mkdir -p go-port\internal\nmap\bin
```

### 3. Place nmap.exe in the embed directory

Copy `nmap.exe` (and any dependencies) to:
```
go-port/internal/nmap/bin/nmap.exe
```

**Important**: nmap has many dependencies (libraries, data files). For a minimal setup, copy:
- `nmap.exe`
- `nmap-data/` folder (contains scripts and databases)
- `libdnet.dll`, `libssh2.dll`, etc. (all .dll files from nmap installation)

You can find these in your nmap installation directory (typically `C:\Program Files (x86)\Nmap\`).

### 4. Verify the structure

```
go-port/
â”œâ”€â”€ internal/
â”‚   â””â”€â”€ nmap/
â”‚       â”œâ”€â”€ bin/
â”‚       â”‚   â”œâ”€â”€ nmap.exe
â”‚       â”‚   â”œâ”€â”€ nmap-data/         (nmap database files)
â”‚       â”‚   â”œâ”€â”€ libdnet.dll
â”‚       â”‚   â”œâ”€â”€ libssh2.dll
â”‚       â”‚   â””â”€â”€ ...other DLLs
â”‚       â”œâ”€â”€ embed.go
â”‚       â””â”€â”€ manager.go
```

### 5. Update embed.go if necessary

The `embed.go` file uses:
```go
//go:embed bin/nmap.exe
var nmapBinary embed.FS
```

If you have additional files (DLLs, data folders), you'll need to update this to:
```go
//go:embed bin/*
var nmapBinary embed.FS
```

And update the `extractNmap()` function in `manager.go` to extract all files.

### 6. Build the executable

```bash
cd go-port
go build -o whitedns.exe ./cmd/whitedns
```

### 7. Verify nmap bundling

Run the executable:
```bash
whitedns.exe
```

On startup, you should see:
```
[+] Bundled nmap initialized at: C:\Users\...\AppData\Local\Temp\whitedns-nmap\nmap.exe
```

## How It Works

1. **Embedding**: Go's `embed` package includes `nmap.exe` in the binary at compile time
2. **Extraction**: When whitedns starts, it extracts nmap to a temporary directory
3. **Path Resolution**: Python code calls `nmap_resolver.get_nmap_executable()` which:
   - Checks the `WHITEDNS_NMAP_PATH` environment variable (set by Go on startup)
   - Falls back to system `nmap` if bundled version isn't available
4. **Execution**: The extracted nmap is executed for scans

## Advantages

âœ… **Single .exe file** - No separate nmap installation needed  
âœ… **Portable** - Works on any Windows machine  
âœ… **Automatic** - Bundled nmap is always available  
âœ… **Fallback** - Still works with system nmap if bundled version fails  
âœ… **Clean** - Temporary files are cleaned up automatically

## Troubleshooting

### "nmap.exe not found" error

1. Verify the file exists: `go-port/internal/nmap/bin/nmap.exe`
2. Rebuild: `go build -o whitedns.exe ./cmd/whitedns`
3. Check the startup log for extraction errors

### "command not found" during scan

This means the temporary directory permissions prevent execution. Try:
```bash
# Run as administrator
whitedns.exe
```

### Size concerns

The bundled executable will be larger (add ~50-100MB for nmap). If size is a concern:
1. Use UPX to compress the executable
2. Keep a separate nmap distribution
3. Use a minimal nmap build

## Advanced: Embedding Multiple Versions

For cross-platform support (Linux, macOS):

1. Create separate binaries for each platform:
   ```
   go-port/internal/nmap/bin/
   â”œâ”€â”€ windows/nmap.exe
   â”œâ”€â”€ linux/nmap
   â””â”€â”€ macos/nmap
   ```

2. Update `embed.go`:
   ```go
   //go:embed bin/windows/* bin/linux/* bin/macos/*
   var nmapBinary embed.FS
   ```

3. Update `manager.go` to select the correct binary based on `runtime.GOOS`

## See Also

- [Go embed package documentation](https://pkg.go.dev/embed)
- [nmap official documentation](https://nmap.org/docs.html)
- [WHITEDNS Architecture](../README.md)
