@echo off
cd /d "%~dp0"
echo Building testscan_local...
go build -o testscan_local.exe ./cmd/testscan_local
if %ERRORLEVEL% EQU 0 (
    echo Build successful!
    dir testscan_local.exe
) else (
    echo Build failed!
)
pause
