package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
)

var db *sql.DB
var rdb *redis.Client
var ctx = context.Background()

type ResolveRequest struct {
	UserID         string  `json:"user_id" binding:"required"`
	OrderID        string  `json:"order_id" binding:"required"`
	ConversationID string  `json:"conversation_id"`
	Complaint      string  `json:"complaint" binding:"required"`
	PhotoURL       string  `json:"photo_url"`
	OrderValue     float64 `json:"order_value"`
}

type Resolution struct {
	Action  string  `json:"action"`
	Amount  float64 `json:"amount"`
	Message string  `json:"message"`
	Reason  string  `json:"reason"`
}

type AgentRequest struct {
	UserID         string  `json:"user_id"`
	OrderID        string  `json:"order_id"`
	ConversationID string  `json:"conversation_id"`
	Complaint      string  `json:"complaint"`
	PhotoURL       string  `json:"photo_url"`
	OrderValue     float64 `json:"order_value"`
}

func newRequestID() string {
	buf := make([]byte, 8)
	if _, err := rand.Read(buf); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(buf)
}

func logJSON(event string, fields map[string]interface{}) {
	payload := map[string]interface{}{
		"event": event,
		"ts_ms": time.Now().UnixMilli(),
	}
	for key, value := range fields {
		if value != nil {
			payload[key] = value
		}
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		log.Printf("event=%s marshal_error=%v", event, err)
		return
	}
	log.Println(string(encoded))
}

func initDB() {
	var err error
	db, err = sql.Open("postgres", os.Getenv("DB_URL"))
	if err != nil {
		log.Fatal("db connect failed:", err)
	}
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS resolutions (
			id SERIAL PRIMARY KEY,
			order_id TEXT,
			user_id TEXT,
			action TEXT,
			reason TEXT,
			created_at TIMESTAMP DEFAULT NOW()
		);
		CREATE TABLE IF NOT EXISTS complaints (
			id SERIAL PRIMARY KEY,
			user_id TEXT,
			order_id TEXT,
			complaint TEXT,
			created_at TIMESTAMP DEFAULT NOW()
		);
	`)
	if err != nil {
		log.Println("db init warning:", err)
	}
}

func initRedis() {
	rdb = redis.NewClient(&redis.Options{
		Addr: os.Getenv("REDIS_ADDR"),
	})
}

func checkRateLimit(userID string) bool {
	key := "rate:" + userID
	count, err := rdb.Incr(ctx, key).Result()
	if err != nil {
		return true
	}
	if count == 1 {
		rdb.Expire(ctx, key, 60*time.Second)
	}
	return count <= 10
}

func saveComplaint(userID, orderID, complaint string) {
	db.Exec("INSERT INTO complaints (user_id, order_id, complaint) VALUES ($1, $2, $3)", userID, orderID, complaint)
}

func saveResolution(orderID, userID, action, reason string) {
	db.Exec("INSERT INTO resolutions (order_id, user_id, action, reason) VALUES ($1, $2, $3, $4)", orderID, userID, action, reason)
}

func callAgent(req AgentRequest, requestID string) Resolution {
	agentURL := os.Getenv("AGENT_SERVICE_URL")
	if agentURL == "" {
		agentURL = "http://localhost:8001"
	}
	body, _ := json.Marshal(req)
	started := time.Now()
	httpReq, err := http.NewRequest(http.MethodPost, agentURL+"/run", bytes.NewBuffer(body))
	if err != nil {
		logJSON("agent_call_failed", map[string]interface{}{
			"request_id": requestID,
			"error":      err.Error(),
		})
		return Resolution{
			Action:  "escalate",
			Message: "Something went wrong. A manager will follow up shortly.",
			Reason:  err.Error(),
		}
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("X-Request-ID", requestID)
	logJSON("agent_call_started", map[string]interface{}{
		"request_id": requestID,
		"user_id":    req.UserID,
		"order_id":   req.OrderID,
	})
	resp, err := http.DefaultClient.Do(httpReq)
	if err != nil {
		logJSON("agent_call_failed", map[string]interface{}{
			"request_id":  requestID,
			"error":       err.Error(),
			"duration_ms": time.Since(started).Milliseconds(),
		})
		return Resolution{
			Action:  "escalate",
			Message: "Something went wrong. A manager will follow up shortly.",
			Reason:  err.Error(),
		}
	}
	defer resp.Body.Close()
	var res Resolution
	json.NewDecoder(resp.Body).Decode(&res)
	logJSON("agent_call_completed", map[string]interface{}{
		"request_id":  requestID,
		"status_code": resp.StatusCode,
		"duration_ms": time.Since(started).Milliseconds(),
		"action":      res.Action,
		"reason":      res.Reason,
	})
	return res
}

func execAction(result Resolution, userID, orderID, requestID string) Resolution {
	payoutURL := os.Getenv("PAYOUT_API_URL")
	if payoutURL == "" {
		logJSON("action_execution_skipped", map[string]interface{}{
			"request_id": requestID,
			"user_id":    userID,
			"order_id":   orderID,
			"action":     result.Action,
			"reason":     "payout_api_unconfigured",
		})
		return result
	}
	switch result.Action {
	case "coupon", "credit", "refund", "replacement":
		started := time.Now()
		body, _ := json.Marshal(map[string]interface{}{
			"user_id":  userID,
			"order_id": orderID,
			"action":   result.Action,
			"amount":   result.Amount,
		})
		logJSON("action_execution_started", map[string]interface{}{
			"request_id": requestID,
			"user_id":    userID,
			"order_id":   orderID,
			"action":     result.Action,
			"amount":     result.Amount,
		})
		resp, err := http.Post(payoutURL+"/execute", "application/json", bytes.NewBuffer(body))
		if err != nil {
			logJSON("action_execution_failed", map[string]interface{}{
				"request_id":  requestID,
				"user_id":     userID,
				"order_id":    orderID,
				"action":      result.Action,
				"duration_ms": time.Since(started).Milliseconds(),
				"error":       err.Error(),
			})
			return result
		}
		defer resp.Body.Close()
		logJSON("action_execution_completed", map[string]interface{}{
			"request_id":  requestID,
			"user_id":     userID,
			"order_id":    orderID,
			"action":      result.Action,
			"duration_ms": time.Since(started).Milliseconds(),
			"status_code": resp.StatusCode,
		})
		if resp.StatusCode != 200 {
			log.Println("payout returned non-200:", resp.StatusCode)
		}
	}
	return result
}

func verifyCaptureHandler(c *gin.Context) {
	fraudURL := os.Getenv("FRAUD_SERVICE_URL")
	if fraudURL == "" {
		fraudURL = "http://localhost:8002"
	}

	// Forward the multipart form as-is to the fraud service
	c.Request.ParseMultipartForm(32 << 20)
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	form := c.Request.MultipartForm
	if form != nil {
		for key, values := range form.Value {
			for _, value := range values {
				_ = writer.WriteField(key, value)
			}
		}
		for _, files := range form.File {
			for _, fh := range files {
				f, err := fh.Open()
				if err != nil {
					continue
				}
				part, err := writer.CreateFormFile("frames", fh.Filename)
				if err != nil {
					f.Close()
					continue
				}
				io.Copy(part, f)
				f.Close()
			}
		}
	}
	writer.Close()

	resp, err := http.Post(fraudURL+"/verify-capture", writer.FormDataContentType(), body)
	if err != nil {
		log.Println("fraud service error:", err)
		c.JSON(200, gin.H{"valid": true, "reason": "fraud service unavailable, defaulting to valid"})
		return
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	c.JSON(200, result)
}

func resolveHandler(c *gin.Context) {
	requestID := c.GetHeader("X-Request-ID")
	if requestID == "" {
		requestID = newRequestID()
	}
	started := time.Now()
	var req ResolveRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		logJSON("resolve_bad_request", map[string]interface{}{
			"request_id": requestID,
			"error":      err.Error(),
		})
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}
	logJSON("resolve_received", map[string]interface{}{
		"request_id": requestID,
		"user_id":    req.UserID,
		"order_id":   req.OrderID,
		"has_photo":  req.PhotoURL != "",
	})

	if !checkRateLimit(req.UserID) {
		logJSON("resolve_rate_limited", map[string]interface{}{
			"request_id": requestID,
			"user_id":    req.UserID,
			"order_id":   req.OrderID,
		})
		c.JSON(429, gin.H{"error": "too many requests"})
		return
	}

	saveComplaint(req.UserID, req.OrderID, req.Complaint)

	agentReq := AgentRequest{
		UserID:         req.UserID,
		OrderID:        req.OrderID,
		ConversationID: req.ConversationID,
		Complaint:      req.Complaint,
		PhotoURL:       req.PhotoURL,
		OrderValue:     req.OrderValue,
	}

	result := callAgent(agentReq, requestID)
	result = execAction(result, req.UserID, req.OrderID, requestID)
	saveResolution(req.OrderID, req.UserID, result.Action, result.Reason)
	logJSON("resolve_completed", map[string]interface{}{
		"request_id":  requestID,
		"user_id":     req.UserID,
		"order_id":    req.OrderID,
		"action":      result.Action,
		"reason":      result.Reason,
		"duration_ms": time.Since(started).Milliseconds(),
	})
	c.Header("X-Request-ID", requestID)
	c.JSON(200, result)
}

func clearSessionHandler(c *gin.Context) {
	userID := c.Query("user_id")
	orderID := c.Query("order_id")
	conversationID := c.Query("conversation_id")

	if userID == "" || orderID == "" {
		c.JSON(400, gin.H{"error": "user_id and order_id required"})
		return
	}

	agentURL := os.Getenv("AGENT_SERVICE_URL")
	if agentURL == "" {
		agentURL = "http://localhost:8001"
	}

	clearURL := agentURL + "/clear_session?user_id=" + userID + "&order_id=" + orderID
	if conversationID != "" {
		clearURL += "&conversation_id=" + conversationID
	}

	resp, err := http.Post(clearURL, "application/json", nil)
	if err != nil {
		c.JSON(500, gin.H{"error": "failed to clear session"})
		return
	}
	defer resp.Body.Close()

	c.JSON(200, gin.H{"status": "cleared", "user_id": userID, "order_id": orderID, "conversation_id": conversationID})
}

func main() {
	godotenv.Load()
	initDB()
	initRedis()

	r := gin.Default()
	r.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type, X-Request-ID")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})
	r.POST("/resolve", resolveHandler)
	r.POST("/verify-capture", verifyCaptureHandler)
	r.POST("/clear_session", clearSessionHandler)
	r.GET("/health", func(c *gin.Context) { c.JSON(200, gin.H{"status": "ok"}) })

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	r.Run(":" + port)
}
