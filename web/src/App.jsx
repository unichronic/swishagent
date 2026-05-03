import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import './App.css'

const API_BASE = import.meta.env.VITE_API_URL || '/api'
const COMPLAINT_CATEGORIES = [
  { id: 'missing_item', label: 'Something missing', hint: 'An item, part of an item, or something expected was missing.' },
  { id: 'wrong_item', label: 'Wrong or different item', hint: 'You got the wrong dish, wrong variant, or something unexpected.' },
  { id: 'quality_issue', label: 'Quality problem', hint: 'Cold, stale, dry, undercooked, or not up to standard.' },
  { id: 'spill_or_damage', label: 'Damaged or spilled', hint: 'Leaking, crushed, broken, opened, or damaged in transit.' },
  { id: 'portion_issue', label: 'Quantity or portion issue', hint: 'The quantity feels less than expected.' },
  { id: 'delivery_issue', label: 'Delivery problem', hint: 'Late, not received, or marked delivered incorrectly.' },
  { id: 'billing_or_coupon', label: 'Billing or coupon issue', hint: 'Charge, coupon, or payment problem for this order.' },
  { id: 'safety_issue', label: 'Safety concern', hint: 'Contamination, allergy risk, or unsafe handling.' },
  { id: 'other', label: 'Something else', hint: 'Use chat if none of these fit well.' },
]

const CATEGORY_CHAT_COPY = {
  missing_item: 'something missing',
  wrong_item: 'the wrong item',
  quality_issue: 'a quality problem',
  spill_or_damage: 'damage or spillage',
  portion_issue: 'a quantity issue',
  delivery_issue: 'a delivery problem',
  billing_or_coupon: 'a billing or coupon issue',
  safety_issue: 'a safety concern',
  other: 'this issue',
}

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
  const [view, setView] = useState('orders') // 'orders', 'intake', or 'chat'
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState(null)
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [selectedItemName, setSelectedItemName] = useState('')
  const [photoFile, setPhotoFile] = useState(null)
  const [awaitingPhoto, setAwaitingPhoto] = useState(false)
  const [showCaptureOverlay, setShowCaptureOverlay] = useState(false)
  const [recording, setRecording] = useState(false)
  const [recordingProgress, setRecordingProgress] = useState(0)
  const [previewStream, setPreviewStream] = useState(null)
  const [recordedCapture, setRecordedCapture] = useState(null)
  const [verifyingCapture, setVerifyingCapture] = useState(false)
  const [captureError, setCaptureError] = useState('')
  const previewVideoRef = useRef(null)
  const recorderRef = useRef(null)
  const recordingIntervalRef = useRef(null)
  const conversationIdRef = useRef('')
  const intakeContextPendingRef = useRef(false)
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

  const resetSupportState = () => {
    if (recordedCapture?.videoUrl) URL.revokeObjectURL(recordedCapture.videoUrl)
    setAwaitingPhoto(false)
    setShowCaptureOverlay(false)
    setRecording(false)
    setRecordingProgress(0)
    setRecordedCapture(null)
    setVerifyingCapture(false)
    setCaptureError('')
    setPreviewStream(null)
    setPhotoFile(null)
    setInput('')
    lastComplaintRef.current = ''
  }

  const buildStructuredComplaint = (userText = '') => {
    const parts = []
    if (selectedCategory?.label && selectedCategory.id !== 'other') {
      parts.push(selectedCategory.label)
    }
    if (selectedItemName) {
      parts.push(`Affected item is ${selectedItemName}.`)
    }
    if (userText.trim()) {
      parts.push(userText.trim())
    }
    return parts.join(' ')
  }

  const getCategoryStarter = (category, itemName) => {
    if (!category) return 'Tell me what went wrong.'
    if (category.id === 'delivery_issue') return 'Tell me what happened with the delivery.'
    if (category.id === 'billing_or_coupon') return 'Tell me what looks wrong with the payment or coupon.'
    if (category.id === 'safety_issue') return 'Tell me what made this feel unsafe.'
    if (category.id === 'missing_item') return `Tell me what seems to be missing from ${itemName || 'the order'}.`
    if (category.id === 'portion_issue') return `Tell me what felt off about the quantity for ${itemName || 'the item'}.`
    return `Tell me what happened with ${itemName || 'the item'}.`
  }

  const getChatIntro = (category, itemName) => {
    const categoryCopy = CATEGORY_CHAT_COPY[category?.id] || 'this issue'
    if (!category) {
      return 'I can help with this order.'
    }
    if (category.id === 'delivery_issue' || itemName === 'Entire order') {
      return `I can help with ${categoryCopy}.`
    }
    return `I can help with ${categoryCopy} for ${itemName}.`
  }

  const openChatWithIntake = (order, category, itemName) => {
    const conversationId = `support-${order.id}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
    conversationIdRef.current = conversationId
    intakeContextPendingRef.current = true
    setSelectedOrder(order)
    setSelectedCategory(category)
    setSelectedItemName(itemName)
    setView('chat')
    resetSupportState()
    // Clear backend session so history doesn't carry over
    axios.post(`${API_BASE}/clear_session?user_id=USER123&order_id=${order.id}&conversation_id=${conversationId}`).catch(() => {})
    setMessages([{
      type: 'bot',
      text: `${getChatIntro(category, itemName)} ${getCategoryStarter(category, itemName)}`,
      meta: { category: category.label, item: itemName },
      timestamp: new Date()
    }])
  }

  const handleGetHelp = (order) => {
    setSelectedOrder(order)
    setSelectedCategory(null)
    setSelectedItemName('')
    resetSupportState()
    setMessages([])
    setView('intake')
  }

  const handleCategorySelect = (category) => {
    if (!selectedOrder || !selectedItemName) return
    setSelectedCategory(category)
    openChatWithIntake(selectedOrder, category, selectedItemName)
  }

  const handleItemSelect = (itemName) => {
    setSelectedItemName(itemName)
    setSelectedCategory(null)
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
      if (recordedCapture?.videoUrl) URL.revokeObjectURL(recordedCapture.videoUrl)
      setRecordedCapture(null)
      setVerifyingCapture(false)
      setCaptureError('')
      setRecordingProgress(0)
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      setPreviewStream(stream)
      setShowCaptureOverlay(true)
      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder
      const chunks = []

      recorder.ondataavailable = e => chunks.push(e.data)
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        setPreviewStream(null)
        setRecording(false)
        setRecordingProgress(0)
        recorderRef.current = null

        const mimeType = recorder.mimeType || 'video/webm'
        const videoBlob = new Blob(chunks, { type: mimeType })
        const videoUrl = URL.createObjectURL(videoBlob)
        try {
          const frames = await extractFrames(videoBlob)
          setRecordedCapture({ videoUrl, frames, order: currentOrder, complaint: currentComplaint })
        } catch {
          URL.revokeObjectURL(videoUrl)
          setAwaitingPhoto(false)
          setShowCaptureOverlay(false)
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
          recordingIntervalRef.current = null
          recorder.stop()
        }
      }, 100)
      recordingIntervalRef.current = interval

    } catch {
      setMessages(prev => [...prev, {
        type: 'bot',
        text: "Couldn't access camera. Please allow camera access and try again.",
        timestamp: new Date()
      }])
    }
  }

  const handleCancelRecording = () => {
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current)
      recordingIntervalRef.current = null
    }
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      recorderRef.current.onstop = null
      recorderRef.current.stop()
      recorderRef.current = null
    }
    if (previewStream) {
      previewStream.getTracks().forEach((track) => track.stop())
    }
    if (recordedCapture?.videoUrl) URL.revokeObjectURL(recordedCapture.videoUrl)
    setPreviewStream(null)
    setShowCaptureOverlay(false)
    setRecording(false)
    setRecordingProgress(0)
    setRecordedCapture(null)
    setVerifyingCapture(false)
    setCaptureError('')
  }

  const handleUseRecordedCapture = async () => {
    if (!recordedCapture || verifyingCapture) return
    setVerifyingCapture(true)
    setCaptureError('')
    try {
      const formData = new FormData()
      recordedCapture.frames.forEach((blob, i) => formData.append('frames', blob, `frame${i}.png`))
      formData.append('user_id', 'USER123')
      formData.append('order_id', recordedCapture.order.id)
      formData.append('complaint', recordedCapture.complaint)

      const result = await axios.post(`${API_BASE}/verify-capture`, formData)

      if (result.data.valid) {
        const captureFile = new File([recordedCapture.frames[0]], 'capture.png', { type: 'image/png' })
        URL.revokeObjectURL(recordedCapture.videoUrl)
        setRecordedCapture(null)
        setShowCaptureOverlay(false)
        setAwaitingPhoto(false)
        handleSendWithContext(captureFile, recordedCapture.order, recordedCapture.complaint, '🎥 Video attached')
      } else {
        setCaptureError("We couldn't verify that capture. Retake it with the order clearly in frame.")
      }
    } catch {
      setCaptureError('Something went wrong while checking the capture. Please try again.')
    } finally {
      setVerifyingCapture(false)
    }
  }

  const uploadPhoto = async (file) => {
    return `https://placeholder.com/${file.name}`
  }

  // Used by live capture — takes explicit order/complaint to avoid stale closure
  const handleSendWithContext = async (photo, order, complaint, displayText = '📷 Photo attached') => {
    setMessages(prev => [...prev, {
      type: 'user',
      text: displayText,
      photo: URL.createObjectURL(photo),
      timestamp: new Date()
    }])
    setLoading(true)
    try {
      const photoUrl = await uploadPhoto(photo)
      const complaintPayload = intakeContextPendingRef.current
        ? buildStructuredComplaint(complaint)
        : complaint
      const response = await axios.post(`${API_BASE}/resolve`, {
        user_id: 'USER123',
        order_id: order.id,
        conversation_id: conversationIdRef.current,
        complaint: complaintPayload,
        photo_url: photoUrl,
        order_value: order.amount
      })
      intakeContextPendingRef.current = false
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
    const rawComplaintText = input || lastComplaintRef.current
    const complaintPayload = intakeContextPendingRef.current
      ? buildStructuredComplaint(rawComplaintText)
      : rawComplaintText
    if (rawComplaintText) lastComplaintRef.current = rawComplaintText
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
        conversation_id: conversationIdRef.current,
        complaint: complaintPayload,
        photo_url: photoUrl,
        order_value: selectedOrder.amount
      })
      intakeContextPendingRef.current = false

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

  if (view === 'intake') {
    const orderItems = selectedOrder?.orderDetails?.items ?? []
    return (
      <div className="support-intake-container">
        <div className="chat-header">
          <button className="back-btn" onClick={() => setView('orders')}>←</button>
          <div className="header-title">Help &amp; Support</div>
        </div>

        <div className="intake-panel">
          <div className="intake-order-row">
            <div>
              <div className="intake-eyebrow">Order</div>
              <div className="intake-order-id">#{selectedOrder?.id}</div>
            </div>
            <div className="intake-order-meta">₹{selectedOrder?.amount}</div>
          </div>

          {!selectedCategory && (
            !selectedItemName ? (
              <>
                <div className="intake-heading">Which item is affected?</div>
                <div className="item-list">
                  {orderItems.map((item) => (
                    <button
                      key={item.name}
                      className="item-card"
                      onClick={() => handleItemSelect(item.name)}
                    >
                      <div className="item-card-main">
                        <span className="item-card-name">{item.name}</span>
                        <span className="item-card-desc">{item.description}</span>
                      </div>
                      <span className="item-card-price">₹{item.price}</span>
                    </button>
                  ))}
                  {orderItems.length > 1 && (
                    <button
                      className="item-card item-card-full"
                      onClick={() => handleItemSelect('Entire order')}
                    >
                      <div className="item-card-main">
                        <span className="item-card-name">Entire order</span>
                        <span className="item-card-desc">Use this if the issue is not limited to one item.</span>
                      </div>
                    </button>
                  )}
                </div>
              </>
            ) : (
              <>
                <div className="intake-heading">What best describes the issue?</div>
                <div className="intake-selection">
                  <span className="selection-label">Item</span>
                  <span className="selection-value">{selectedItemName}</span>
                  <button className="selection-change" onClick={() => setSelectedItemName('')}>Change</button>
                </div>

                <div className="category-list">
                  {COMPLAINT_CATEGORIES.map((category) => (
                    <button
                      key={category.id}
                      className="category-card"
                      onClick={() => handleCategorySelect(category)}
                    >
                      <span className="category-text">{category.label}</span>
                      <span className="category-arrow">›</span>
                    </button>
                  ))}
                </div>
              </>
            )
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="chat-container">
      <div className="chat-header">
        <button className="back-btn" onClick={() => setView('intake')}>←</button>
        <div className="header-title">Help</div>
      </div>
      
      <div className="chat-subheader">
        <span className="order-badge-small">Order #{selectedOrder?.id}</span>
        {selectedCategory && <span className="context-pill">{selectedCategory.label}</span>}
        {selectedItemName && <span className="context-pill context-pill-muted">{selectedItemName}</span>}
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
            placeholder={selectedItemName ? `Tell us what went wrong with ${selectedItemName.toLowerCase()}...` : 'Describe your issue...'}
            rows="1"
          />
          <button 
            onClick={() => handleSend()} 
            disabled={loading || awaitingPhoto || recording || (!input.trim() && !photoFile)}
            className="send-btn"
          >
            ➤
          </button>
        </div>
      </div>

      {showCaptureOverlay && (
        <div className="capture-overlay">
          {recordedCapture ? (
            <video src={recordedCapture.videoUrl} controls playsInline className="capture-overlay-video" />
          ) : (
            <video ref={previewVideoRef} autoPlay muted playsInline className="capture-overlay-video" />
          )}
          <div className="capture-overlay-top">
            <button className="capture-close" onClick={handleCancelRecording}>×</button>
            <div className="capture-status">
              {!recordedCapture && <span className="capture-status-dot" />}
              <span>
                {recordedCapture
                  ? 'Review capture'
                  : recording
                    ? 'Recording live capture'
                    : 'Preparing camera'}
              </span>
            </div>
          </div>
          <div className="capture-overlay-bottom">
            {recordedCapture ? (
              <div className="capture-review-panel">
                {captureError && <div className="capture-review-error">{captureError}</div>}
                <div className="capture-review-actions">
                  <button className="capture-review-btn secondary" onClick={handleStartRecording} disabled={verifyingCapture}>
                    Retake
                  </button>
                  <button className="capture-review-btn" onClick={handleUseRecordedCapture} disabled={verifyingCapture}>
                    {verifyingCapture ? 'Checking…' : 'Use video'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="capture-progress-shell">
                <div className="capture-progress-track">
                  <div className="capture-progress-fill" style={{ width: `${recordingProgress * 100}%` }} />
                </div>
                <div className="capture-progress-text">
                  {recording ? 'Keep the order in frame for 5 seconds' : 'Starting camera...'}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default App
