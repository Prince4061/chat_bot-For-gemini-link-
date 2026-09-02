import React, { useState, useRef, useEffect } from 'react';
import { 
  Send, 
  Sparkles, 
  User, 
  KeyRound, 
  ShoppingBag, 
  CreditCard, 
  HelpCircle, 
  Loader2,
  Lock,
  ArrowRight,
  ShieldCheck,
  Zap,
  Info
} from 'lucide-react';
import MessageItem from './MessageItem';
import PaymentModal from './PaymentModal';

export default function ChatView({
  messages,
  onSendMessage,
  loading,
  userType,
  setUserType,
  currentSessionId
}) {
  const [inputMessage, setInputMessage] = useState('');
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showResellerModal, setShowResellerModal] = useState(false);
  
  // Quick Reseller Form State
  const [resellerPhone, setResellerPhone] = useState('');
  const [resellerCode, setResellerCode] = useState('');
  const [selectedProduct, setSelectedProduct] = useState('Gemini Advanced');

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!inputMessage.trim() || loading) return;
    const msg = inputMessage;
    setInputMessage('');
    onSendMessage(msg);
  };

  const handleQuickAction = (text) => {
    setInputMessage(text);
    onSendMessage(text);
  };

  const handleQuickResellerSubmit = (e) => {
    e.preventDefault();
    if (!resellerPhone || !resellerCode) return;
    const formattedQuery = `Reseller Request: Phone: ${resellerPhone}, Code: ${resellerCode}. Claim product: ${selectedProduct}`;
    setShowResellerModal(false);
    onSendMessage(formattedQuery);
  };

  return (
    <div className="flex-1 flex flex-col h-screen bg-slate-950 text-slate-100 relative overflow-hidden">
      
      {/* Top Header Bar */}
      <header className="h-14 border-b border-slate-800/80 px-6 flex items-center justify-between bg-slate-950/80 backdrop-blur-md z-10 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm text-slate-100">AI Vending Assistant</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-500/30 font-medium flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              OpenAI GPT-4o
            </span>
          </div>
        </div>

        {/* Mode Selector & Quick Helper */}
        <div className="flex items-center gap-2">
          {userType === 'reseller' ? (
            <button
              onClick={() => setShowResellerModal(true)}
              className="flex items-center gap-1.5 px-3 py-1 bg-teal-950/80 hover:bg-teal-900 border border-teal-500/40 text-teal-300 text-xs font-semibold rounded-lg shadow-sm transition-all"
            >
              <KeyRound className="w-3.5 h-3.5 text-teal-400" />
              Claim Link Helper
            </button>
          ) : (
            <button
              onClick={() => setShowPaymentModal(true)}
              className="flex items-center gap-1.5 px-3 py-1 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300 text-xs font-semibold rounded-lg shadow-sm transition-all"
            >
              <CreditCard className="w-3.5 h-3.5 text-emerald-400" />
              UPI QR Pay
            </button>
          )}

          <div className="flex items-center bg-slate-900 rounded-lg p-0.5 border border-slate-800">
            <button
              onClick={() => setUserType('customer')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                userType === 'customer'
                  ? 'bg-emerald-600 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Customer
            </button>
            <button
              onClick={() => setUserType('reseller')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                userType === 'reseller'
                  ? 'bg-teal-500 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Reseller
            </button>
          </div>
        </div>
      </header>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        
        {/* Empty State / Welcome Screen */}
        {messages.length === 0 && (
          <div className="max-w-2xl mx-auto text-center py-10 px-4">
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-xl shadow-emerald-950/50">
              <Sparkles className="w-7 h-7 text-slate-950" />
            </div>

            <h2 className="text-xl font-bold text-slate-100 mb-2">
              Automated Digital Product Vending & Reseller Hub
            </h2>
            <p className="text-xs text-slate-400 mb-8 max-w-lg mx-auto leading-relaxed">
              Powered by Deep Agent & OpenAI. Buy private digital tool invites with dynamic live rates or verify as a reseller to claim single-use links instantly with credits.
            </p>

            {/* Quick Action Suggestion Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-left">
              <div
                onClick={() => handleQuickAction('Show me available digital products and current live prices')}
                className="p-3.5 rounded-xl bg-slate-900/80 hover:bg-slate-800/80 border border-slate-800/80 hover:border-emerald-500/40 cursor-pointer transition-all group"
              >
                <div className="flex items-center gap-2 font-semibold text-xs text-emerald-400 mb-1">
                  <ShoppingBag className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
                  <span>Browse Products & Live Rates</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  View Gemini Advanced, Claude Pro, ChatGPT Plus with real-time margin rates.
                </p>
              </div>

              <div
                onClick={() => {
                  setUserType('reseller');
                  setShowResellerModal(true);
                }}
                className="p-3.5 rounded-xl bg-slate-900/80 hover:bg-slate-800/80 border border-slate-800/80 hover:border-teal-500/40 cursor-pointer transition-all group"
              >
                <div className="flex items-center gap-2 font-semibold text-xs text-teal-400 mb-1">
                  <KeyRound className="w-4 h-4 text-teal-400 group-hover:scale-110 transition-transform" />
                  <span>Reseller Login & Claim Link</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Verify with Phone + 4-Digit Passcode to instantly burn and claim single-use links.
                </p>
              </div>

              <div
                onClick={() => handleQuickAction('How can I become a reseller and buy credit packs?')}
                className="p-3.5 rounded-xl bg-slate-900/80 hover:bg-slate-800/80 border border-slate-800/80 hover:border-slate-700 cursor-pointer transition-all group"
              >
                <div className="flex items-center gap-2 font-semibold text-xs text-slate-300 mb-1">
                  <CreditCard className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
                  <span>Buy Reseller Credits</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Check bulk discount packages (10, 50, 100 packs) and Admin UPI payment info.
                </p>
              </div>

              <div
                onClick={() => handleQuickAction('I am a reseller. Check my wallet credit balance')}
                className="p-3.5 rounded-xl bg-slate-900/80 hover:bg-slate-800/80 border border-slate-800/80 hover:border-slate-700 cursor-pointer transition-all group"
              >
                <div className="flex items-center gap-2 font-semibold text-xs text-slate-300 mb-1">
                  <Lock className="w-4 h-4 text-teal-400 group-hover:scale-110 transition-transform" />
                  <span>Check My Credits</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Check remaining balance before claiming stock.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Messages List */}
        {messages.map((msg, idx) => (
          <MessageItem
            key={idx}
            message={msg}
            onOpenPaymentQr={() => setShowPaymentModal(true)}
          />
        ))}

        {/* Loading Spinner */}
        {loading && (
          <div className="flex gap-3.5 max-w-4xl mx-auto px-4 py-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center shrink-0 shadow-md">
              <Loader2 className="w-4 h-4 text-slate-950 animate-spin" />
            </div>
            <div className="glass-panel rounded-2xl p-4 text-xs text-slate-300 flex items-center gap-2.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
              <span>Deep Agent is planning & executing tools...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form Bar */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/90 shrink-0">
        <div className="max-w-4xl mx-auto">
          <form onSubmit={handleSubmit} className="relative flex items-center">
            <input
              ref={inputRef}
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder={
                userType === 'reseller'
                  ? "Enter phone & 4-digit code (e.g. 'Phone: 9876543210, Code: 1234, Claim Gemini')"
                  : "Ask for product prices, order details, or share payment UTR reference..."
              }
              disabled={loading}
              className="w-full py-3.5 pl-4 pr-12 bg-slate-900/90 border border-slate-700/80 rounded-2xl text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 shadow-inner"
            />
            <button
              type="submit"
              disabled={!inputMessage.trim() || loading}
              className="absolute right-2.5 p-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:hover:bg-emerald-600 text-slate-950 font-bold rounded-xl transition-all shadow-md active:scale-95"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>

          <div className="flex items-center justify-between text-[11px] text-slate-400 px-2 mt-2">
            <span className="flex items-center gap-1">
              <ShieldCheck className="w-3 h-3 text-emerald-400" />
              Automated Single-Use Link Burning & Verification
            </span>
            <span>Press Enter to send</span>
          </div>
        </div>
      </div>

      {/* UPI Payment Modal */}
      <PaymentModal
        isOpen={showPaymentModal}
        onClose={() => setShowPaymentModal(false)}
        upiId="resellerpay@upi"
        payeeName="Digital Vending Admin"
      />

      {/* Quick Reseller Helper Modal */}
      {showResellerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl p-6 text-slate-200">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-teal-400 font-bold text-sm">
                <KeyRound className="w-4 h-4" />
                <span>Reseller Fast Claim Helper</span>
              </div>
              <button
                onClick={() => setShowResellerModal(false)}
                className="text-slate-400 hover:text-slate-200 text-xs"
              >
                Cancel
              </button>
            </div>

            <form onSubmit={handleQuickResellerSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1 font-medium">Registered Phone Number</label>
                <input
                  type="text"
                  placeholder="e.g. 9876543210"
                  value={resellerPhone}
                  onChange={(e) => setResellerPhone(e.target.value)}
                  required
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-teal-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">4-Digit Secret Passcode</label>
                <input
                  type="password"
                  maxLength={4}
                  placeholder="e.g. 1234"
                  value={resellerCode}
                  onChange={(e) => setResellerCode(e.target.value)}
                  required
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-teal-500 font-mono tracking-widest text-center text-sm"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Select Product to Claim</label>
                <select
                  value={selectedProduct}
                  onChange={(e) => setSelectedProduct(e.target.value)}
                  className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-slate-100 focus:outline-none focus:border-teal-500"
                >
                  <option value="Gemini Advanced">Gemini Advanced (1-Year Invite Link) - 1 Credit</option>
                  <option value="Claude Pro">Claude Pro (Private Org Invite) - 1 Credit</option>
                  <option value="ChatGPT Plus">ChatGPT Plus (1-Month Workspace) - 1 Credit</option>
                  <option value="Canva Pro">Canva Pro (Lifetime Edu Invite) - 1 Credit</option>
                  <option value="Office 365">Office 365 (5-Device Enterprise) - 1 Credit</option>
                </select>
              </div>

              <div className="p-2.5 bg-teal-950/40 border border-teal-500/20 rounded-xl text-[11px] text-teal-300">
                💡 1 Credit will be deducted automatically, and your single-use link will be delivered instantly in chat.
              </div>

              <button
                type="submit"
                className="w-full py-2.5 bg-gradient-to-r from-teal-600 to-emerald-600 hover:from-teal-500 hover:to-emerald-500 text-slate-950 font-bold rounded-xl transition-all shadow-md"
              >
                Authenticate & Claim Link
              </button>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
