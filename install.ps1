<#
.SYNOPSIS
    Ambyte Self-Hosted Installer
#>

$ErrorActionPreference = "Stop"

# --- UI Helpers ---
function Write-Header {
    Write-Host "=======================================================" -ForegroundColor Cyan
    Write-Host "             Ambyte Self-Hosted Installer              " -ForegroundColor Cyan
    Write-Host "=======================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Set-Env {
    param([string]$Key, [string]$Value)
    $envFile = ".env"
    
    if (Test-Path $envFile) {
        $content = Get-Content $envFile -Raw
        # Use regex to replace existing key or append if missing
        $regex = "(?m)^$([regex]::Escape($Key))=.*$"
        
        if ($content -match $regex) {
            $content = $content -replace $regex, "$Key=$Value"
        } else {
            if ($content.Length -gt 0 -and $content[-1] -ne "`n") {
                $content += "`n"
            }
            $content += "$Key=$Value`n"
        }
        
        # Write back using UTF8 (without BOM to ensure Docker compatibility)
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText("$PWD\$envFile", $content, $utf8NoBom)
    }
}

Write-Header

# 1. Pre-flight checks
if (-Not (Get-Command "docker" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: Docker is not installed. Please install Docker Desktop first." -ForegroundColor Red
    exit 1
}

if (-Not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: Git is not installed. Please install Git first." -ForegroundColor Red
    exit 1
}

# 2. Clone or Update Repository
if (-Not (Test-Path "ambyte")) {
    Write-Host "📦 Cloning Ambyte repository..." -ForegroundColor Green
    git clone https://github.com/ambyte-ai/ambyte.git
    Set-Location "ambyte"
} else {
    Write-Host "📦 Ambyte directory exists. Updating..." -ForegroundColor Green
    Set-Location "ambyte"
    git pull origin master
}

# 3. Handle .env file
if (-Not (Test-Path ".env")) {
    Write-Host "⚙️  Setting up configuration environment..." -ForegroundColor Green
    Copy-Item ".env.example" ".env"
}

$envContent = Get-Content ".env" -Raw

# 4. Prompt for Clerk Keys (Auth)
if ($envContent -notmatch "(?m)^NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_") {
    Write-Host ""
    Write-Host "Ambyte requires Clerk for authentication (https://clerk.com)." -ForegroundColor Yellow
    
    $clerk_pub = Read-Host "Enter your NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"
    $clerk_secret = Read-Host "Enter your CLERK_SECRET_KEY"
    $clerk_issuer = Read-Host "Enter your CLERK_ISSUER URL (e.g. https://noble-fox-42.clerk.accounts.dev)"
    $superuser_email = Read-Host "Enter your FIRST_SUPERUSER email (e.g. admin@company.com)"

    Set-Env "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" $clerk_pub
    Set-Env "CLERK_SECRET_KEY" $clerk_secret
    Set-Env "CLERK_ISSUER" $clerk_issuer
    Set-Env "FIRST_SUPERUSER" $superuser_email
    Set-Env "ENVIRONMENT" "production"
} else {
    Write-Host "✅ Clerk keys already configured." -ForegroundColor Green
}

# Refresh Env Content
$envContent = Get-Content ".env" -Raw

# 5. Generate Cryptographic & Secret Keys
if ($envContent -notmatch "(?m)^SECRET_KEY=.*[a-zA-Z0-9]") {
    Write-Host "`n🔐 Generating Cryptographic Audit Keys and Secrets..." -ForegroundColor Green
    
    # We pipe the Python script directly into the Docker container's stdin to avoid Windows path/volume mounting quirks
    $pyScript = @"
import secrets
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

priv = ed25519.Ed25519PrivateKey.generate()
pub = priv.public_key()

print(secrets.token_urlsafe(32))
print(priv.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw, encryption_algorithm=serialization.NoEncryption()).hex())
print(pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw).hex())
"@

    $keys = $pyScript | docker run -i --rm python:3.11-slim bash -c "pip install cryptography -q >/dev/null 2>&1 && python -"
    
    if ($keys.Count -eq 3) {
        Set-Env "SECRET_KEY" $keys[0]
        Set-Env "AMBYTE_AUDIT_SYSTEM_PRIVATE_KEY" $keys[1]
        Set-Env "AMBYTE_SYSTEM_PUBLIC_KEY" $keys[2]
        Write-Host "✅ Keys generated successfully." -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to generate keys." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✅ Cryptographic keys already configured." -ForegroundColor Green
}

# 6. Start Backend Services
Write-Host "`n🚀 Starting database and core APIs..." -ForegroundColor Green
docker compose -f docker-compose.prod.yml up -d db redis qdrant minio create-bucket api

# 7. Wait for API to be ready
Write-Host "⏳ Waiting for database migrations and API to boot (this may take a moment)..." -ForegroundColor Yellow
while ($true) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/ping" -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            break
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}
Write-Host "✅ API is healthy." -ForegroundColor Green

# 8. Bootstrap Database (Creates Admin & Ingest Keys)
$envContent = Get-Content ".env" -Raw
if ($envContent -notmatch "(?m)^AMBYTE_API_KEY=sk_live_") {
    Write-Host "`n🌱 Bootstrapping Database & Generating System API Keys..." -ForegroundColor Green
    
    $initOutput = docker compose -f docker-compose.prod.yml exec -T api uv run python src/scripts/init_db.py
    $joinedOutput = $initOutput -join "`n"
    
    $adminKeyMatch = [regex]::Match($joinedOutput, 'sk_live_[a-zA-Z0-9_-]+')
    $ingestKeyMatch = [regex]::Match($joinedOutput, 'sk_ingest_[a-zA-Z0-9_-]+')

    if ($adminKeyMatch.Success) {
        $adminKey = $adminKeyMatch.Value
        $ingestKey = $ingestKeyMatch.Value
        
        Set-Env "AMBYTE_API_KEY" $adminKey
        Set-Env "INGEST_WORKER_API_KEY" $ingestKey
        Set-Env "CONNECTOR_API_KEY" $adminKey
        Set-Env "AMBYTE_INGEST_CONTROL_PLANE_API_KEY" $ingestKey
    } else {
        Write-Host "❌ Failed to capture API keys. Database might already be initialized." -ForegroundColor Red
    }
} else {
    Write-Host "✅ Database already bootstrapped." -ForegroundColor Green
    $adminKey = [regex]::Match($envContent, '(?m)^AMBYTE_API_KEY=(sk_live_.*)').Groups[1].Value
}

# 9. Build Frontend and Start Workers
Write-Host "`n🏗️ Building Next.js Dashboard (Baking in Clerk Keys)..." -ForegroundColor Green
docker compose -f docker-compose.prod.yml build web

Write-Host "`n🚀 Starting final services (Workers and Dashboard)..." -ForegroundColor Green
docker compose -f docker-compose.prod.yml up -d

Write-Host "`n=======================================================" -ForegroundColor Green
Write-Host "🎉 AMBYTE DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
Write-Host "`nDashboard URL:     " -NoNewline; Write-Host "http://localhost:3000" -ForegroundColor Cyan
Write-Host "Control Plane API: " -NoNewline; Write-Host "http://localhost:8000" -ForegroundColor Cyan

Write-Host "`nYour Admin Root API Key (Save this!):" -ForegroundColor Yellow
Write-Host "👉 $adminKey"

Write-Host "`n💡 Note: To use the PDF AI ingestion pipeline, add your OPENAI_API_KEY and VOYAGE_API_KEY to the .env file and restart the containers." -ForegroundColor Yellow
Write-Host "`nTo view logs: docker compose -f docker-compose.prod.yml logs -f"
Write-Host "To stop:      docker compose -f docker-compose.prod.yml down`n"