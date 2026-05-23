$dir = "c:\Users\tajirax\Downloads\free internt\white  proxy 9.32\go-port"
Set-Location $dir
Write-Host "Building testscan_local from $dir"
& go build -o testscan_local.exe ./cmd/testscan_local
if ($LASTEXITCODE -eq 0) {
    Write-Host "Build successful!"
    Get-Item testscan_local.exe | Format-List
} else {
    Write-Host "Build failed with code $LASTEXITCODE"
}
