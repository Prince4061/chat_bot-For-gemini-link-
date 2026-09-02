# 🤖 AI Deep Agent: Automated Digital Product Vending & Reseller Management System

An enterprise-grade, autonomous AI Deep Agent built with **Flask**, **LangChain**, **LangGraph**, and **OpenAI GPT-4o / GPT-4o-mini**, paired with a **ChatGPT-style React Frontend** and **Admin Control Dashboard**.

---

## 🌟 Core Features & Architecture

### 1. 🛍️ Customer Flow (Dynamic Pricing & UPI Delivery)
- **Role Detection:** Bot dynamically identifies whether the user is a Regular Customer or Reseller.
- **Dynamic Pricing Engine:** Calculates selling price in real-time from database:
  $$\text{Customer Selling Price} = \text{Base Price} + \left(\text{Base Price} \times \frac{\text{Admin Margin \%}}{100}\right)$$
- **Payment & Delivery:** Generates structured UPI/QR payment instructions (`admin_upi_id`). Customer submits 12-digit UTR to instantly receive their private single-use invite link.

### 2. 🔑 Reseller Flow (4-Digit Passcode & Instant Link Burning)
- **2-Factor Verification:** Requires registered **Phone Number** + **4-Digit Secret Passcode** (e.g. `Phone: 9876543210, Code: 1234`).
- **Wallet Credits Balance:** Checks live credits (1 Credit = 1 Single-Use Link).
- **Atomic Link Burning (Single-Use Guarantee):**
  - Atomically marks the link as **Burned / Claimed** with recipient phone and timestamp.
  - Guarantees the link can **never be redistributed to anyone else**.
  - Automatically deducts credits and logs the transaction.
- **Unregistered Reseller Onboarding:** If verification fails, explains bulk credit packages (e.g. 10 Credits = ₹1,500) and provides Admin UPI payment info to buy credits.

### 3. ⚙️ Full Admin Control Dashboard (React)
- **Products & Margin Control:** Change live Margin % (e.g. 30% to 50%) and the Deep Agent quotes the new price to customers in the very next turn.
- **Single-Use Links Inventory:** Bulk upload 50+ invite links/keys via multi-line textarea with real-time stock counters and claim audit logs.
- **Reseller Management:** Add resellers, set/reset 4-digit passcodes, and top-up or deduct wallet credits.
- **Customer Orders & UPI Approvals:** Approve pending UPI orders with 1-click single-use link fulfillment.
- **Evolution API (WhatsApp) Webhook & Live Simulator:** Test incoming WhatsApp webhook payloads directly in the browser.

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10+
- Node.js 18+ (Node 25 tested)

### 1. Backend Setup (Flask + Deep Agent)

```bash
# Clone or navigate to the project directory
cd "G:\Chat_BOT\Chat BOt"

# Install Python dependencies
pip install -r requirements.txt

# Configure your .env file
# Add your OpenAI API key in .env or via the Admin Dashboard UI
```

### 2. Start the Application

You can run the application in two ways:

#### Option A: Unified Server (Serves both React UI and API on Port 5000)
```bash
python app.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser!

#### Option B: Developer Mode (Vite Hot-Reload + Flask Backend)
**Terminal 1 (Backend):**
```bash
python app.py
```
**Terminal 2 (Frontend):**
```bash
cd frontend
npm run dev
```
Open **[http://localhost:3000](http://localhost:3000)** for live hot-reload development.

---

## 📱 Evolution API (WhatsApp) Integration

The bot is designed to be 100% platform-independent.

### Webhook Endpoint:
```
POST http://YOUR_SERVER_IP:5000/api/webhook/evolution
```
- Subscribe to event: `MESSAGES_UPSERT`
- The system parses incoming WhatsApp messages, matches user sessions by phone number, invokes the Deep Agent, and automatically sends the response back to WhatsApp via Evolution API's `/message/sendText` endpoint.

---

## 📁 Project Structure

```
├── agent.md                    # Global Deep Agent memory & rules
├── agent_core.py               # Deep Agent execution runner (OpenAI LLM + LangGraph)
├── agent_tools.py              # LangChain tools (pricing, auth, link dispenser, orders)
├── app.py                      # Flask REST API, chat endpoints, admin endpoints & webhooks
├── database.py                 # SQLite + SQLAlchemy models & atomic link claiming
├── evolution_service.py        # WhatsApp Evolution API integration service
├── requirements.txt            # Python dependencies
├── deep_agents/                # Deep Agent implementation
│   ├── __init__.py
│   ├── agent.py                # create_deep_agent with write_todos planning
│   └── backends.py             # FileSystemBackend, StateBackend, StoreBackend
└── frontend/                   # React + Vite + Tailwind CSS + Lucide
    ├── src/
    │   ├── App.jsx             # Main ChatGPT layout controller
    │   ├── components/
    │   │   ├── Sidebar.jsx     # ChatGPT-style sidebar & session manager
    │   │   ├── ChatView.jsx    # Interactive conversation interface
    │   │   ├── MessageItem.jsx # Rich message, single-use link badge & QR pay
    │   │   ├── PaymentModal.jsx# Dynamic UPI QR Code modal
    │   │   ├── AdminDashboard.jsx # Admin control center
    │   │   ├── ProductManager.jsx # Dynamic margin slider & products
    │   │   ├── InventoryManager.jsx # Bulk link upload & claim audit trail
    │   │   ├── ResellerManager.jsx  # Reseller passcodes & wallet credits
    │   │   ├── OrderManager.jsx     # Customer orders & UTR approvals
    │   │   ├── SettingsManager.jsx  # Admin UPI & OpenAI credentials
    │   │   └── EvolutionSimulator.jsx # WhatsApp live webhook simulator
```

---

## 🔑 Default Seeded Demo Accounts

### Sample Resellers:
1. **Rahul Sharma (Verified Reseller)**
   - Phone: `9876543210`
   - Secret Code: `1234`
   - Credits: `25`
2. **Amit Patel (Reseller Pro)**
   - Phone: `9123456780`
   - Secret Code: `8899`
   - Credits: `10`
3. **Pooja Verma (Tech Store)**
   - Phone: `9988776655`
   - Secret Code: `4321`
   - Credits: `3`

### Sample Products:
- **Gemini Advanced (1-Year Invite Link)**: Base: ₹450 | Margin: 40% | Live Price: ₹630 | Cost: 1 Credit
- **Claude Pro (Private Org Invite)**: Base: ₹600 | Margin: 35% | Live Price: ₹810 | Cost: 1 Credit
- **ChatGPT Plus (1-Month Workspace)**: Base: ₹350 | Margin: 45% | Live Price: ₹507.50 | Cost: 1 Credit
- **Canva Pro (Lifetime Edu Invite)**: Base: ₹100 | Margin: 100% | Live Price: ₹200 | Cost: 1 Credit
- **Office 365 (5-Device Enterprise)**: Base: ₹200 | Margin: 50% | Live Price: ₹300 | Cost: 1 Credit
