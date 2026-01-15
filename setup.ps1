#
# DummyProx - One-Click Setup Script for Windows
# Run with: powershell -ExecutionPolicy Bypass -File setup.ps1
#

$ErrorActionPreference = "Stop"

function Write-Color {
    param([string]$Text, [string]$Color = "White")
    Write-Host $Text -ForegroundColor $Color
}

Clear-Host
Write-Color "
  ____                                  ____
 |  _ \ _   _ _ __ ___  _ __ ___  _   _|  _ \ _ __ _____  __
 | | | | | | | '_ `` _ \| '_ `` _ \| | | | |_) | '__/ _ \ \/ /
 | |_| | |_| | | | | | | | | | | | |_| |  __/| | | (_) >  <
 |____/ \__,_|_| |_| |_|_| |_| |_|\__, |_|   |_|  \___/_/\_\
                                  |___/
" "Cyan"

Write-Color "Nested Proxmox Manager - One-Click Setup" "White"
Write-Color "=========================================" "White"
Write-Host ""

# Check for Docker
Write-Color "[1/5] Checking for Docker..." "Yellow"

$dockerPath = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerPath) {
    Write-Color "Error: Docker is not installed." "Red"
    Write-Host ""
    Write-Host "Please install Docker Desktop for Windows:"
    Write-Host "  https://docs.docker.com/desktop/install/windows-install/"
    Write-Host ""
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker not running"
    }
    Write-Color "√ Docker is installed and running" "Green"
} catch {
    Write-Color "Error: Docker daemon is not running." "Red"
    Write-Host "Please start Docker Desktop and try again."
    Write-Host ""
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# Check for docker-compose
Write-Color "[2/5] Checking for Docker Compose..." "Yellow"

$useCompose = $false
try {
    docker compose version 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $useCompose = $true
        Write-Color "√ Docker Compose is available" "Green"
    }
} catch {
    Write-Color "Warning: Docker Compose not found, using docker build instead" "Yellow"
}

# Clean up old containers and images
Write-Color "[3/5] Cleaning up old containers and images..." "Yellow"
try {
    if ($useCompose) {
        $null = docker compose down --rmi all 2>&1
    } else {
        $null = docker rm -f dummyprox 2>&1
        $null = docker rmi dummyprox 2>&1
    }
} catch {
    # Ignore errors - container/image may not exist
}
Write-Color "√ Cleanup complete" "Green"

# Build and run
Write-Color "[4/5] Building and starting DummyProx..." "Yellow"
Write-Host ""

if ($useCompose) {
    docker compose build --no-cache
    docker compose up -d
} else {
    docker build --no-cache -t dummyprox .
    docker run -d -p 8080:80 --name dummyprox dummyprox
}

if ($LASTEXITCODE -ne 0) {
    Write-Color "Error: Failed to start DummyProx" "Red"
    Write-Host ""
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host ""
Write-Color "√ DummyProx is now running" "Green"

# Open browser
Write-Color "[5/5] Opening web interface..." "Yellow"
$url = "http://localhost:8080"
Start-Process $url

Write-Host ""
Write-Color "=========================================" "Green"
Write-Color "  DummyProx is ready!" "Green"
Write-Color "=========================================" "Green"
Write-Host ""
Write-Host "  Web Interface: " -NoNewline
Write-Color "http://localhost:8080" "Cyan"
Write-Host ""
Write-Host "  Commands:"
Write-Host "    Stop:    docker stop dummyprox"
Write-Host "    Start:   docker start dummyprox"
Write-Host "    Logs:    docker logs -f dummyprox"
Write-Host "    Remove:  docker rm -f dummyprox"
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
