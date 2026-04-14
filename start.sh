#!/bin/bash

echo "🚀 Starting Swish Support System"
echo ""

# Kill existing processes
pkill -f "uvicorn agent_service" 2>/dev/null
pkill -f "uvicorn fraud_service" 2>/dev/null
pkill -f "uvicorn order_service" 2>/dev/null
pkill -f "uvicorn kitchen_service" 2>/dev/null
pkill -f "uvicorn fleet_service" 2>/dev/null
pkill -f "uvicorn trust_service" 2>/dev/null
pkill -f "go run main.go" 2>/dev/null

# Start infrastructure (All databases + Redis)
echo "📦 Starting infrastructure..."
docker compose up -d

# Wait for databases to be ready
echo "⏳ Waiting for databases to be ready..."
sleep 8

# Start microservices
echo "🏗️  Starting microservices..."

echo "   📦 Order Service (port 8084)..."
nohup python -m uvicorn order_service:app --port 8084 >> /tmp/order.log 2>&1 &

echo "   🍳 Kitchen Service (port 8081)..."
nohup python -m uvicorn kitchen_service:app --port 8081 >> /tmp/kitchen.log 2>&1 &

echo "   🚚 Fleet Service (port 8082)..."
nohup python -m uvicorn fleet_service:app --port 8082 >> /tmp/fleet.log 2>&1 &

echo "   🛡️  Trust Service (port 8083)..."
nohup python -m uvicorn trust_service:app --port 8083 >> /tmp/trust.log 2>&1 &

# Start agent and fraud services
echo "🤖 Starting agent service (port 8001)..."
nohup python -m uvicorn agent_service:app --port 8001 >> /tmp/agent.log 2>&1 &

echo "🔍 Starting fraud service (port 8002)..."
nohup python -m uvicorn fraud_service:app --port 8002 >> /tmp/fraud.log 2>&1 &

# Start Go backend
echo "⚙️  Starting backend (port 8080)..."
nohup go run main.go >> /tmp/go.log 2>&1 &

# Wait for services to start
sleep 5

# Health checks
echo ""
echo "🏥 Health checks:"
curl -s --max-time 5 http://localhost:8001/health > /tmp/agent_health.txt 2>&1
curl -s --max-time 5 http://localhost:8002/health > /tmp/fraud_health.txt 2>&1
curl -s --max-time 5 http://localhost:8080/health > /tmp/go_health.txt 2>&1
curl -s --max-time 5 http://localhost:8081/health > /tmp/kitchen_health.txt 2>&1
curl -s --max-time 5 http://localhost:8082/health > /tmp/fleet_health.txt 2>&1
curl -s --max-time 5 http://localhost:8083/health > /tmp/trust_health.txt 2>&1
curl -s --max-time 5 http://localhost:8084/health > /tmp/order_health.txt 2>&1

echo "   Agent:   $(cat /tmp/agent_health.txt)"
echo "   Fraud:   $(cat /tmp/fraud_health.txt)"
echo "   Backend: $(cat /tmp/go_health.txt)"
echo "   Kitchen: $(cat /tmp/kitchen_health.txt)"
echo "   Fleet:   $(cat /tmp/fleet_health.txt)"
echo "   Trust:   $(cat /tmp/trust_health.txt)"
echo "   Order:   $(cat /tmp/order_health.txt)"

echo ""
echo "✅ All services running:"
echo "   - Backend API:     http://localhost:8080"
echo "   - Agent Service:   http://localhost:8001"
echo "   - Kitchen Service: http://localhost:8081"
echo "   - Fleet Service:   http://localhost:8082"
echo "   - Trust Service:   http://localhost:8083"
echo "   - Order Service:   http://localhost:8084"
echo ""
echo "📊 Databases:"
echo "   - Agent DB:   localhost:5432"
echo "   - Order DB:   localhost:5433"
echo "   - Kitchen DB: localhost:5434"
echo "   - Fleet DB:   localhost:5435"
echo "   - Trust DB:   localhost:5436"
echo "   - Redis:      localhost:6379"
echo ""
echo "🌐 To start the web UI:"
echo "   cd web && npm run dev"
echo ""
echo "📝 View logs:"
echo "   tail -f /tmp/agent.log"
echo "   tail -f /tmp/kitchen.log"
echo "   tail -f /tmp/fleet.log"
echo "   tail -f /tmp/trust.log"
echo "   tail -f /tmp/order.log"
echo ""
echo "🛑 To stop:"
echo "   ./stop.sh"
