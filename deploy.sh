#!/bin/bash
set -euo pipefail

echo "🚀 Deploying Swish Support System (Infrastructure Only)"

if [ ! -f ".env" ]; then
  echo "❌ .env is missing. Copy .env.example to .env and configure deployment secrets."
  exit 1
fi

require_env() {
  local key="$1"
  if ! grep -Eq "^${key}=.+" .env; then
    echo "❌ Missing required env var in .env: ${key}"
    exit 1
  fi
}

has_env() {
  local key="$1"
  grep -Eq "^${key}=.+" .env
}

require_env "DB_URL"
require_env "REDIS_ADDR"
require_env "AGENT_SERVICE_URL"

if has_env "LANGFUSE_PUBLIC_KEY" || has_env "LANGFUSE_SECRET_KEY"; then
  require_env "LANGFUSE_PUBLIC_KEY"
  require_env "LANGFUSE_SECRET_KEY"
  require_env "LANGFUSE_HOST"
  echo "📊 Langfuse tracing: enabled"
else
  echo "📊 Langfuse tracing: disabled (missing keys)"
fi

# Start infrastructure services
docker compose up -d --build

echo "✅ Infrastructure started:"
echo "   - PostgreSQL: localhost:5432"
echo "   - Redis: localhost:6379"
echo ""
echo "📝 To view logs:"
echo "   docker compose logs -f"
echo ""
echo "🛑 To stop:"
echo "   docker compose down"
echo ""
echo "💡 For local development, use ./scripts/start.sh to start all services"
