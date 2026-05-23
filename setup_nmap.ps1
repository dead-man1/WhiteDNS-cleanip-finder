$ErrorActionPreference = "Stop"

$nmapPaths = @(
    "C:\Program Files (x86)\Nmap",
    "C:\Program Files\Nmap",
    "C:\nmap"
)

$embedDir = "go-port\internal\nmap\bin"
$found = $false

Write-Host "Looking for nmap installation..." -ForegroundColor Cyan

foreach ($path in $nmapPaths) {
    if (Test-Path "$path\nmap.exe") {
        Write-Host "[+] Found nmap at: $path" -ForegroundColor Green
        
        # Create embed directory
        if (!(Test-Path $embedDir)) {
            New-Item -ItemType Directory -Path $embedDir -Force | Out-Null
            Write-Host "[*] Created embedding directory: $embedDir" -ForegroundColor Yellow
        }
        
        # Copy main executable
        Write-Host "[*] Copying nmap.exe..." -ForegroundColor Gray
        Copy-Item "$path\nmap.exe" "$embedDir\nmap.exe" -Force
        
        # Copy DLL dependencies
        Write-Host "[*] Copying dependencies..." -ForegroundColor Gray
        Get-Item "$path\*.dll" -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item $_.FullName "$embedDir\" -Force
        }
        
        # Copy nmap-data folder if it exists
        if (Test-Path "$path\nmap-data") {
            Write-Host "[*] Copying nmap-data folder..." -ForegroundColor Gray
            Copy-Item "$path\nmap-data" "$embedDir\nmap-data" -Recurse -Force
        }
        
        # Copy scripts folder if it exists
        if (Test-Path "$path\scripts") {
            Write-Host "[*] Copying scripts folder..." -ForegroundColor Gray
            Copy-Item "$path\scripts" "$embedDir\scripts" -Recurse -Force
        }
        
        Write-Host "" -ForegroundColor Green
        Write-Host "[+] nmap successfully copied to $embedDir" -ForegroundColor Green
        Write-Host "" -ForegroundColor Green
        Write-Host "Next steps:" -ForegroundColor Cyan
        Write-Host "  1. cd go-port" -ForegroundColor Gray
        Write-Host "  2. go build -o whitedns.exe ./cmd/whitedns" -ForegroundColor Gray
        Write-Host "  3. Run: .\whitedns.exe" -ForegroundColor Gray
        Write-Host "" -ForegroundColor Gray
        
        $found = $true
        break
    }
}

if (!$found) {
    Write-Host "[!] nmap not found in standard locations" -ForegroundColor Red
    Write-Host "" -ForegroundColor Gray
    Write-Host "Please install nmap or specify its location:" -ForegroundColor Yellow
    Write-Host "  - Download: https://nmap.org/download.html" -ForegroundColor Gray
    Write-Host "  - Chocolatey: choco install nmap" -ForegroundColor Gray
    Write-Host "  - Manual path: Edit this script and add your path to `$nmapPaths" -ForegroundColor Gray
    exit 1
}
