#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================================${NC}"
echo -e "${BLUE}             Ambyte Self-Hosted Installer              ${NC}"
echo -e "${BLUE}=======================================================${NC}"
echo ""

# 1. Pre-flight checks
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: Git is not installed. Please install Git first.${NC}"
    exit 1
fi

# 2. Clone Repository
if [ ! -d "ambyte" ]; then
    echo -e "📦 Cloning Ambyte repository..."
    git clone https://github.com/ambyte-ai/ambyte.git
    cd ambyte
else
    echo -e "📦 Ambyte directory exists. Updating..."
    cd ambyte
    git pull origin master
fi

# 3. Handle .env file
if [ ! -f .env ]; then
    echo -e "⚙️  Setting up configuration environment..."
    cp .env.example .env
fi

# Helper function to write/replace env vars safely
set_env() {
    local key=$1
    local val=$2
    # If the key exists, replace it. Otherwise, append it.
    if grep -q "^${key}=" .env; then
        sed -i.bak "s|^${key}=.*|${key}=${val}|" .env
        rm -f .env.bak
    else
        echo "${key}=${val}" >> .env
    fi
}

# 4. Prompt for Clerk Keys (Auth)
if ! grep -q "^NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_" .env; then
    echo ""
    echo -e "${YELLOW}Ambyte requires Clerk for authentication (https://clerk.com).${NC}"
    read -p "Enter your NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: " clerk_pub
    read -p "Enter your CLERK_SECRET_KEY: " clerk_secret
    read -p "Enter your CLERK_ISSUER URL (e.g. https://noble-fox-42.clerk.accounts.dev): " clerk_issuer
    read -p "Enter your FIRST_SUPERUSER email (e.g. admin@company.com): " superuser_email

    set_env "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" "$clerk_pub"
    set_env "CLERK_SECRET_KEY" "$clerk_secret"
    set_env "CLERK_ISSUER" "$clerk_issuer"
    set_env "FIRST_SUPERUSER" "$superuser_email"
    set_env "ENVIRONMENT" "production"
else
    echo -e "✅ Clerk keys already configured."
fi

# 5. Generate Cryptographic & Secret Keys (Zero-dependency via ephemeral Docker)
if ! grep -q "^SECRET_KEY=.*[a-zA-Z0-9]" .env; then
    echo -e "\n🔐 Generating Cryptographic Audit Keys and Secrets..."
    docker run --rm -v $(pwd):/app -w /app python:3.11-slim bash -c "\
    pip install cryptography -q >/dev/null 2>&1 && \
    python -c \"
import secrets
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
priv = ed25519.Ed25519PrivateKey.generate()
pub = priv.public_key()
print(secrets.token_urlsafe(32))
print(priv.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw, encryption_algorithm=serialization.NoEncryption()).hex())
print(pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw).hex())
    \"" > keys.tmp

    SECRET_KEY=$(sed '1q;d' keys.tmp)
    AUDIT_PRIV_KEY=$(sed '2q;d' keys.tmp)
    AUDIT_PUB_KEY=$(sed '3q;d' keys.tmp)
    rm keys.tmp

    set_env "SECRET_KEY" "$SECRET_KEY"
    set_env "AMBYTE_AUDIT_SYSTEM_PRIVATE_KEY" "$AUDIT_PRIV_KEY"
    set_env "AMBYTE_SYSTEM_PUBLIC_KEY" "$AUDIT_PUB_KEY"

    echo -e "✅ Keys generated successfully."
else
    echo -e "✅ Cryptographic keys already configured."
fi

# 6. Start Backend Services
echo -e "\n🚀 Starting database and core APIs..."
# We start everything except 'web' so Next.js build doesn't happen yet
docker compose -f docker-compose.prod.yml up -d db redis qdrant minio create-bucket api

# 7. Wait for API to be ready (which means migrations are done)
echo -e "⏳ Waiting for database migrations and API to boot (this may take a moment)..."
# We loop until the /ping endpoint returns HTTP 200
while ! curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ping | grep -q "200"; do
    sleep 3
done
echo -e "✅ API is healthy."

# 8. Bootstrap Database (Creates Admin & Ingest Keys)
if ! grep -q "^AMBYTE_API_KEY=sk_live_" .env; then
    echo -e "\n🌱 Bootstrapping Database & Generating System API Keys..."
    INIT_OUTPUT=$(docker compose -f docker-compose.prod.yml exec -T api uv run python src/scripts/init_db.py)

    ADMIN_API_KEY=$(echo "$INIT_OUTPUT" | grep -o 'sk_live_[a-zA-Z0-9_-]*' | head -n 1)
    INGEST_API_KEY=$(echo "$INIT_OUTPUT" | grep -o 'sk_ingest_[a-zA-Z0-9_-]*' | head -n 1)

    if [ -n "$ADMIN_API_KEY" ]; then
        set_env "AMBYTE_API_KEY" "$ADMIN_API_KEY"
        set_env "INGEST_WORKER_API_KEY" "$INGEST_API_KEY"
        set_env "CONNECTOR_API_KEY" "$ADMIN_API_KEY"
        set_env "AMBYTE_INGEST_CONTROL_PLANE_API_KEY" "$INGEST_API_KEY"
    else
        echo -e "${RED}Failed to capture API keys. Database might already be initialized.${NC}"
    fi
else
    echo -e "✅ Database already bootstrapped."
    ADMIN_API_KEY=$(grep "^AMBYTE_API_KEY=" .env | cut -d '=' -f2)
fi

# 9. Build Frontend and Start Workers
echo -e "\n🏗️ Building Next.js Dashboard (Baking in Clerk Keys)..."
# Now we build the web container. It will pull the Clerk keys from the .env we just updated.
docker compose -f docker-compose.prod.yml build web

echo -e "\n🚀 Starting final services (Workers and Dashboard)..."
docker compose -f docker-compose.prod.yml up -d

echo -e "\n${GREEN}=======================================================${NC}"
echo -e "${GREEN}🎉 AMBYTE DEPLOYMENT COMPLETE!${NC}"
echo -e "${GREEN}=======================================================${NC}"
echo -e "\n${BLUE}Dashboard URL:${NC}    http://localhost:3000"
echo -e "${BLUE}Control Plane API:${NC} http://localhost:8000"
echo ""
echo -e "${YELLOW}Your Admin Root API Key (Save this!):${NC}"
echo -e "👉 ${ADMIN_API_KEY}"
echo ""
echo -e "💡 ${YELLOW}Note:${NC} To use the PDF AI ingestion pipeline, add your OPENAI_API_KEY and VOYAGE_API_KEY to the .env file and restart the containers."
echo ""
echo -e "To view logs: docker compose -f docker-compose.prod.yml logs -f"
echo -e "To stop:      docker compose -f docker-compose.prod.yml down"