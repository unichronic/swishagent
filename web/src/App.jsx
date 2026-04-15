import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import './App.css'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

// Mock orders data with actual menu items
const MOCK_ORDERS = [
  {
    id: 'ORD001', // Butter Chicken + Fries
    status: 'delivered',
    amount: 478,
    date: '18th Apr 2026, 01:15 pm',
    items: ['https://via.placeholder.com/80x80/ef4444/ffffff?text=🍗', 'https://via.placeholder.com/80x80/f59e0b/ffffff?text=🍟'],
    orderDetails: {
      items: [
        { name: 'Butter Chicken Rice Bowl', price: 269, quantity: 1, description: 'Creamy butter chicken with jeera rice' },
        { name: 'Peri Peri French Fries', price: 209, quantity: 1, description: 'French fries sprinkled with peri peri masala' }
      ],
      deliveryTime: '45 mins',
      restaurant: 'Swish Cloud Kitchen',
      deliveryAddress: '123 MG Road, Bangalore',
      paymentMethod: 'UPI'
    }
  },
  {
    id: 'ORD002', // Salad + Sandwich + Coffee
    status: 'delivered',
    amount: 627,
    date: '17th Apr 2026, 08:45 pm',
    items: [
      'https://via.placeholder.com/80x80/22c55e/ffffff?text=🥗',
      'https://via.placeholder.com/80x80/f97316/ffffff?text=🥪',
      'https://via.placeholder.com/80x80/8b5cf6/ffffff?text=☕'
    ],
    orderDetails: {
      items: [
        { name: 'Caesar Salad (Non-Veg)', price: 259, quantity: 1, description: 'Fresh veggies & chicken with caesar dressing' },
        { name: 'Grilled Paneer Club Sandwich', price: 219, quantity: 1, description: 'Paneer club sandwich, served fresh in 4 slices' },
        { name: 'Classic Cold Coffee', price: 159, quantity: 1, description: 'Chilled creamy coffee, as classic as it gets' }
      ],
      deliveryTime: '38 mins',
      restaurant: 'Swish Cloud Kitchen',
      deliveryAddress: '456 Indiranagar, Bangalore',
      paymentMethod: 'Credit Card'
    }
  },
  {
    id: 'ORD003', // Vada Shots + Maggi
    status: 'delivered',
    amount: 168,
    date: '16th Apr 2026, 02:30 pm',
    items: [
      'https://via.placeholder.com/80x80/06b6d4/ffffff?text=🥟',
      'https://via.placeholder.com/80x80/10b981/ffffff?text=🍜'
    ],
    orderDetails: {
      items: [
        { name: 'Batata Vada Shots', price: 89, quantity: 1, description: 'Bite-sized batata vadas served with green chutney (6 pieces)' },
        { name: 'Classic Maggi', price: 79, quantity: 1, description: 'Your favorite noodles with the signature masala' }
      ],
      deliveryTime: '25 mins',
      restaurant: 'Swish Cloud Kitchen',
      deliveryAddress: '789 Koramangala, Bangalore',
      paymentMethod: 'Cash on Delivery'
    }
  },
  {
    id: 'ORD004', // Chicken Curry + Pasta + 2 Beverages
    status: 'delivered',
    amount: 756,
    date: '15th Apr 2026, 07:20 pm',
    items: [
      'https://via.placeholder.com/80x80/eab308/ffffff?text=🍛',
      'https://via.placeholder.com/80x80/ec4899/ffffff?text=🍝',
      'https://via.placeholder.com/80x80/14b8a6/ffffff?text=🥤',
      'https://via.placeholder.com/80x80/a855f7/ffffff?text=🍫'
    ],
    orderDetails: {
      items: [
        { name: 'Dhaba Style Chicken Curry Rice Bowl', price: 269, quantity: 1, description: 'Rustic dhaba-style chicken curry with jeera rice' },
        { name: 'Veg Pink Sauce Pasta', price: 219, quantity: 1, description: 'Penne in creamy pink sauce with veggies and herbs' },
        { name: 'Roohafza Sharbat', price: 79, quantity: 1, description: 'Nostalgic Rooh Afza cooler (sharbat), fragrant and refreshing (450 ml)' },
        { name: 'Dark Chocolate Oreo Shake', price: 189, quantity: 1, description: 'Creamy chocolate shake with Oreo chunks (450 ml)' }
      ],
      deliveryTime: '52 mins',
      restaurant: 'Swish Cloud Kitchen',
      deliveryAddress: '321 Whitefield, Bangalore',
      paymentMethod: 'Paytm'
    }
  },
  {
    id: 'ORD005', // 2 Pasta + Samosa
    status: 'delivered',
    amount: 437,
    date: '14th Apr 2026, 12:45 pm',
    items: [
      'https://via.placeholder.com/80x80/f59e0b/ffffff?text=🥙',
      'https://via.placeholder.com/80x80/3b82f6/ffffff?text=🍲'
    ],
    orderDetails: {
      items: [
        { name: 'Veg Alfredo Penne', price: 209, quantity: 1, description: 'Creamy penne with veggies and herbs' },
        { name: 'Egg Curry Rice Bowl', price: 209, quantity: 1, description: 'Egg curry with jeera basmati rice' },
        { name: 'Mini Punjabi Aloo Samosa', price: 99, quantity: 1, description: 'As classic as samosa gets, comes with chutneys (3 pieces)' }
      ],
      deliveryTime: '35 mins',
      restaurant: 'Swish Cloud Kitchen',
      deliveryAddress: '555 HSR Layout, Bangalore',
      paymentMethod: 'Google Pay'
    }
  }
]

function App() {
  const [view, setView] = useState('orders') // 'orders' or 'chat'
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState(null)
  const [photoFile, setPhotoFile] = useState(null)
  const [awaitingPhoto, setAwaitingPhoto] = useState(false)
  const [recording, setRecording] = useState(false)
  const [recordingProgress, setRecordingProgress] = useState(0)
  const [previewStream, setPreviewStream] = useState(null)
  const previewVideoRef = useRef(null)
  const lastComplaintRef = useRef('')
  const messagesEndRef = useRef(null)
  const fileInputRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    if (previewVideoRef.current && previewStream) {
      previewVideoRef.current.srcObject = previewStream
    }
  }, [previewStream])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleGetHelp = (order) => {
    setSelectedOrder(order)
    setView('chat')
    setAwaitingPhoto(false)
    setRecording(false)
    setRecordingProgress(0)
    setPreviewStream(null)
    setPhotoFile(null)
    lastComplaintRef.current = ''
    // Clear backend session so history doesn't carry over
    axios.post(`${API_BASE}/clear_session?user_id=USER123&order_id=${order.id}`).catch(() => {})
    setMessages([{
      type: 'bot',
      text: `Hi! I'm here to help with order #${order.id}. What seems to be the issue?`,
      timestamp: new Date()
    }])
  }

  const handleFileSelect = (e) => {
    const file = e.target.files[0]
    if (file && file.type.startsWith('image/')) {
      setPhotoFile(file)
    }
  }

  // Extract a single frame from a video element at its current time — PNG (lossless) for ELA accuracy
  const extractFrame = (video) => {
    const canvas = document.createElement('canvas')
    canvas.width = 480
    canvas.height = Math.round(video.videoHeight * (480 / video.videoWidth))
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
    return new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
  }

  // Extract 5 frames from a video blob at t=0, t=1.25, t=2.5, t=3.75, t=5
  // 5 frames gives SSIM more temporal resolution to detect static/loop captures
  const extractFrames = (videoBlob) => {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(videoBlob)
      const video = document.createElement('video')
      video.muted = true
      video.preload = 'auto'
      const frames = []
      const timestamps = [0.01, 1.25, 2.5, 3.75, 5]

      const captureAt = (ts) => new Promise((res) => {
        const onSeeked = async () => {
          video.removeEventListener('seeked', onSeeked)
          res(await extractFrame(video))
        }
        video.addEventListener('seeked', onSeeked)
        video.currentTime = Math.min(ts, video.duration - 0.05)
      })

      video.addEventListener('loadedmetadata', async () => {
        try {
          for (const ts of timestamps) {
            frames.push(await captureAt(ts))
          }
          URL.revokeObjectURL(url)
          resolve(frames)
        } catch (e) {
          URL.revokeObjectURL(url)
          reject(e)
        }
      })
      video.addEventListener('error', () => { URL.revokeObjectURL(url); reject(new Error('video load failed')) })
      video.src = url
    })
  }

  const handleStartRecording = async () => {
    // Capture stable refs at call time to avoid stale closure in onstop
    const currentOrder = selectedOrder
    const currentComplaint = lastComplaintRef.current

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      setPreviewStream(stream)
      const recorder = new MediaRecorder(stream)
      const chunks = []

      recorder.ondataavailable = e => chunks.push(e.data)
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        setPreviewStream(null)
        setRecording(false)
        setRecordingProgress(0)

        const mimeType = recorder.mimeType || 'video/webm'
        const videoBlob = new Blob(chunks, { type: mimeType })
        try {
          const frames = await extractFrames(videoBlob)

          const formData = new FormData()
          frames.forEach((blob, i) => formData.append('frames', blob, `frame${i}.png`))
          formData.append('user_id', 'USER123')
          formData.append('order_id', currentOrder.id)
          formData.append('complaint', currentComplaint)

          const result = await axios.post(`${API_BASE}/verify-capture`, formData)

          if (result.data.valid) {
            setAwaitingPhoto(false)
            const captureFile = new File([frames[0]], 'capture.png', { type: 'image/png' })
            // Call handleSend with explicit order/complaint to avoid stale closure
            handleSendWithContext(captureFile, currentOrder, currentComplaint)
          } else {
            setAwaitingPhoto(false)
            setMessages(prev => [...prev, {
              type: 'bot',
              text: "Sorry, we couldn't process your request.",
              timestamp: new Date()
            }])
          }
        } catch {
          setAwaitingPhoto(false)
          setMessages(prev => [...prev, {
            type: 'bot',
            text: 'Something went wrong with the capture. Please try again.',
            timestamp: new Date()
          }])
        }
      }

      recorder.start()
      setRecording(true)

      // Count up progress over 5 seconds
      let elapsed = 0
      const interval = setInterval(() => {
        elapsed += 100
        setRecordingProgress(Math.min(elapsed / 5000, 1))
        if (elapsed >= 5000) {
          clearInterval(interval)
          recorder.stop()
        }
      }, 100)

    } catch {
      setMessages(prev => [...prev, {
        type: 'bot',
        text: "Couldn't access camera. Please allow camera access and try again.",
        timestamp: new Date()
      }])
    }
  }

  const uploadPhoto = async (file) => {
    return `https://placeholder.com/${file.name}`
  }

  // Used by live capture — takes explicit order/complaint to avoid stale closure
  const handleSendWithContext = async (photo, order, complaint) => {
    setMessages(prev => [...prev, {
      type: 'user',
      text: '📷 Photo attached',
      photo: URL.createObjectURL(photo),
      timestamp: new Date()
    }])
    setLoading(true)
    try {
      const photoUrl = await uploadPhoto(photo)
      const response = await axios.post(`${API_BASE}/resolve`, {
        user_id: 'USER123',
        order_id: order.id,
        complaint,
        photo_url: photoUrl,
        order_value: order.amount
      })
      setMessages(prev => [...prev, {
        type: 'bot',
        text: response.data.message,
        action: response.data.action,
        amount: response.data.amount,
        timestamp: new Date()
      }])
      if (response.data.action === 'live_capture') setAwaitingPhoto(true)
    } catch {
      setMessages(prev => [...prev, { type: 'bot', text: 'Sorry, something went wrong. Please try again.', timestamp: new Date() }])
    } finally {
      setLoading(false)
    }
  }

  const handleSend = async (overridePhoto = null) => {
    const photo = overridePhoto || photoFile
    if (!input.trim() && !photo) return

    const userMessage = {
      type: 'user',
      text: input || '📷 Photo attached',
      photo: photo ? URL.createObjectURL(photo) : null,
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    const complaintText = input || lastComplaintRef.current
    if (input) lastComplaintRef.current = input
    setInput('')
    setLoading(true)

    try {
      let photoUrl = null
      if (photo) {
        photoUrl = await uploadPhoto(photo)
        setPhotoFile(null)
      }

      const response = await axios.post(`${API_BASE}/resolve`, {
        user_id: 'USER123',
        order_id: selectedOrder.id,
        complaint: complaintText,
        photo_url: photoUrl,
        order_value: selectedOrder.amount
      })

      const botMessage = {
        type: 'bot',
        text: response.data.message,
        action: response.data.action,
        amount: response.data.amount,
        timestamp: new Date()
      }

      setMessages(prev => [...prev, botMessage])
      if (response.data.action === 'live_capture') {
        setAwaitingPhoto(true)
      }
    } catch (error) {
      const errorMessage = {
        type: 'bot',
        text: 'Sorry, something went wrong. Please try again.',
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (view === 'orders') {
    return (
      <div className="orders-container">
        <div className="orders-header">
          <button className="back-btn">←</button>
          <h1>Your Orders</h1>
        </div>

        <div className="orders-list">
          {MOCK_ORDERS.map((order) => (
            <div key={order.id} className="order-card">
              <div className="order-header-row">
                <div className="order-status">
                  <span className="status-text">Order {order.status}</span>
                  <span className="status-icon">✓</span>
                </div>
                <div className="order-amount">₹{order.amount}</div>
                <button className="order-menu">⋮</button>
              </div>
              
              <div className="order-date">Placed at {order.date}</div>
              
              <div className="order-items">
                {order.items.map((item, idx) => (
                  <img key={idx} src={item} alt="Item" className="order-item-img" />
                ))}
              </div>

              <div className="order-item-names">
                {order.orderDetails.items.map((item, idx) => (
                  <span key={idx} className="item-name">{item.name}</span>
                ))}
              </div>

              <div className="order-actions">
                <button className="btn-secondary">Rate Order</button>
                <button 
                  className="btn-primary"
                  onClick={() => handleGetHelp(order)}
                >
                  Get Help
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="chat-container">
      <div className="chat-header">
        <button className="back-btn" onClick={() => setView('orders')}>←</button>
        <div className="header-title">Help</div>
      </div>
      
      <div className="chat-subheader">
        <span className="order-badge-small">Order #{selectedOrder?.id}</span>
      </div>

      <div className="messages-container">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.type}`}>
            <div className="message-content">
              {msg.photo && (
                <img src={msg.photo} alt="Uploaded" className="message-photo" />
              )}
              <p>{msg.text}</p>
              {msg.action === 'live_capture' && idx === messages.length - 1 && (
                <div className="inline-capture">
                  {recording ? (
                    <div className="recording-indicator">
                      <video ref={previewVideoRef} autoPlay muted playsInline className="camera-preview" />
                      <div className="recording-bar-row">
                        <div className="recording-dot" />
                        <div className="recording-bar">
                          <div className="recording-fill" style={{ width: `${recordingProgress * 100}%` }} />
                        </div>
                        <span>Recording…</span>
                      </div>
                    </div>
                  ) : (
                    <button className="live-capture-btn" onClick={handleStartRecording}>
                      📷 Record 5s Video
                    </button>
                  )}
                </div>
              )}
              {msg.action && msg.action !== 'info' && msg.action !== 'escalate' && msg.action !== 'live_capture' && msg.amount > 0 && (
                <div className="action-badge">
                  {msg.action === 'coupon' && `✓ ₹${msg.amount} Coupon Applied`}
                  {msg.action === 'credit' && `✓ ₹${msg.amount} Credit Added`}
                  {msg.action === 'refund' && `✓ ₹${msg.amount} Refund Initiated`}
                </div>
              )}
              {msg.action === 'replacement' && (
                <div className="action-badge">✓ Replacement Order Placed</div>
              )}
            </div>
            <div className="message-time">
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
          </div>
        ))}
        {loading && (
          <div className="message bot">
            <div className="message-content">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-container">
        {photoFile && (
          <div className="photo-preview">
            <img src={URL.createObjectURL(photoFile)} alt="Preview" />
            <button onClick={() => setPhotoFile(null)} className="remove-photo">×</button>
          </div>
        )}
        <div className="input-wrapper">
          <button 
            className="attach-btn"
            onClick={() => fileInputRef.current?.click()}
            title="Attach photo"
          >
            📎
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            accept="image/*"
            style={{ display: 'none' }}
          />
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Describe your issue..."
            rows="1"
          />
          <button 
            onClick={handleSend} 
            disabled={loading || awaitingPhoto || recording || (!input.trim() && !photoFile)}
            className="send-btn"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  )
}

export default App
