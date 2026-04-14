#!/bin/bash

echo "🛑 Stopping Swish Support System"

# Stop services
pkill -f "uvicorn agent_service"
pkill -f "uvicorn fraud_service"
pkill -f "uvicorn order_service"
pkill -f "uvicorn kitchen_service"
pkill -f "uvicorn fleet_service"
pkill -f "uvicorn trust_service"
pkill -f "go run main.go"

# Stop infrastructure
docker compose down

echo "✅ All services stopped"
