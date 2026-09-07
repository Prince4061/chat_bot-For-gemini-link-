import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Sparkles,
  KeyRound,
  ShoppingBag,
  CreditCard,
  Menu,
  PenSquare
} from 'lucide-react';
import MessageItem from './MessageItem';
import PaymentModal from './PaymentModal';

export default function ChatView({
  messages,
  onSendMessage,
  loading,
  currentSessionId,
  onOpenSidebar,
  onNewSession
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
    setInputMessage('');
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
    <div className="flex-1 flex flex-col h-[100dvh] bg-[#212121] text-[#ececec] relative overflow-hidden">

      {/* Top Header Bar */}
      <header className="h-14 px-3 sm:px-4 flex items-center justify-between bg-[#212121] z-10 shrink-0">
        <div className="flex items-center gap-1">
          {/* Hamburger: opens the chat-history drawer on mobile */}
          <button
            onClick={onOpenSidebar}
            className="md:hidden p-2 -ml-1 text-[#ececec] hover:bg-[#2f2f2f] rounded-lg"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <span className="font-medium text-base text-[#ececec]">Vending</span>
        </div>

        {/* Quick helpers */}
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => setShowResellerModal(true)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-[#b4b4b4] hover:text-white hover:bg-[#2f2f2f] text-xs font-medium rounded-lg transition-colors"
            title="Reseller login"
          >
            <KeyRound className="w-4 h-4" />
            <span className="hidden sm:inline">Reseller</span>
          </button>
          <button
            onClick={() => setShowPaymentModal(true)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-[#b4b4b4] hover:text-white hover:bg-[#2f2f2f] text-xs font-medium rounded-lg transition-colors"
            title="UPI QR pay"
          >
            <CreditCard className="w-4 h-4" />
            <span className="hidden sm:inline">Pay</span>
          </button>
          <button
            onClick={onNewSession}
            className="p-2 text-[#b4b4b4] hover:text-white rounded-lg hover:bg-[#2f2f2f]"
            aria-label="New chat"
          >
            <PenSquare className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto py-4">
        
        {/* Empty State / Welcome Screen — the assistant asks who you are first */}
        {messages.length === 0 && (
          <div className="max-w-2xl mx-auto text-center py-16 px-4">
            <h2 className="text-2xl font-semibold text-[#ececec] mb-2">
              Aap Customer hain ya Reseller?
            </h2>
            <p className="text-sm text-[#8e8ea0] mb-8 max-w-md mx-auto leading-relaxed">
              Batayein aap kaun hain — main uske hisaab se madad karunga.
            </p>

            {/* Two clear choices */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto text-left">
              <button
                onClick={() => handleQuickAction('Main ek customer hoon. Mujhe available products aur unke live prices dikhao.')}
                className="p-4 rounded-2xl bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/5 cursor-pointer transition-colors group"
              >
                <div className="w-10 h-10 mb-3 rounded-full bg-white/10 flex items-center justify-center text-[#ececec]">
                  <ShoppingBag className="w-5 h-5" />
                </div>
                <div className="font-medium text-sm text-[#ececec] mb-0.5">I'm a Customer</div>
                <p className="text-xs text-[#8e8ea0] leading-relaxed">
                  Products aur live rates dekho, UPI se kharido.
                </p>
              </button>

              <button
                onClick={() => handleQuickAction('Main ek reseller hoon.')}
                className="p-4 rounded-2xl bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-white/5 cursor-pointer transition-colors group"
              >
                <div className="w-10 h-10 mb-3 rounded-full bg-white/10 flex items-center justify-center text-[#ececec]">
                  <KeyRound className="w-5 h-5" />
                </div>
                <div className="font-medium text-sm text-[#ececec] mb-0.5">I'm a Reseller</div>
                <p className="text-xs text-[#8e8ea0] leading-relaxed">
                  Phone + 4-digit code se verify karke link claim karo.
                </p>
              </button>
            </div>

            <button
              onClick={() => handleQuickAction('Reseller kaise banein aur wallet me paise kaise daalein?')}
              className="mt-4 text-xs text-[#8e8ea0] hover:text-[#ececec] transition-colors inline-flex items-center gap-1"
            >
              <CreditCard className="w-3.5 h-3.5" />
              Reseller banna chahte ho? Wallet top-up kaise hota hai →
            </button>
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

        {/* Typing indicator */}
        {loading && (
          <div className="flex gap-3 max-w-3xl mx-auto w-full px-3 py-3">
            <div className="w-7 h-7 rounded-full bg-white flex items-center justify-center shrink-0">
              <Sparkles className="w-3.5 h-3.5 text-black" />
            </div>
            <div className="flex items-center gap-1.5 pt-2.5">
              <span className="w-2 h-2 rounded-full bg-[#b4b4b4] animate-bounce" style={{ animationDelay: '0ms' }}></span>
              <span className="w-2 h-2 rounded-full bg-[#b4b4b4] animate-bounce" style={{ animationDelay: '150ms' }}></span>
              <span className="w-2 h-2 rounded-full bg-[#b4b4b4] animate-bounce" style={{ animationDelay: '300ms' }}></span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form Bar */}
      <div className="px-3 pb-4 pt-2 bg-[#212121] shrink-0" style={{ paddingBottom: 'max(1rem, env(safe-area-inset-bottom))' }}>
        <div className="max-w-3xl mx-auto">
          <form onSubmit={handleSubmit} className="relative flex items-end bg-[#2f2f2f] rounded-[26px] transition-colors">
            <input
              ref={inputRef}
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="Message Vending…"
              disabled={loading}
              className="w-full py-4 pl-5 pr-14 bg-transparent rounded-[26px] text-sm text-[#ececec] placeholder-[#8e8ea0] focus:outline-none"
            />
            <button
              type="submit"
              disabled={!inputMessage.trim() || loading}
              className="absolute right-2 bottom-2 p-2 bg-white hover:bg-white/90 disabled:bg-[#676767] disabled:cursor-not-allowed text-black rounded-full transition-colors"
              aria-label="Send"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <p className="text-center text-[11px] text-[#8e8ea0] mt-2">
            Single-use links delivered instantly after payment or verification.
          </p>
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
          <div className="w-full max-w-md bg-[#2f2f2f] border border-white/10 rounded-2xl p-6 text-[#ececec]">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-[#ececec] font-bold text-sm">
                <KeyRound className="w-4 h-4" />
                <span>Reseller Fast Claim Helper</span>
              </div>
              <button
                onClick={() => setShowResellerModal(false)}
                className="text-[#8e8ea0] hover:text-[#ececec] text-xs"
              >
                Cancel
              </button>
            </div>

            <form onSubmit={handleQuickResellerSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Registered Phone Number</label>
                <input
                  type="text"
                  placeholder="e.g. 9876543210"
                  value={resellerPhone}
                  onChange={(e) => setResellerPhone(e.target.value)}
                  required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                />
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">4-Digit Secret Passcode</label>
                <input
                  type="password"
                  maxLength={4}
                  placeholder="e.g. 1234"
                  value={resellerCode}
                  onChange={(e) => setResellerCode(e.target.value)}
                  required
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15 font-mono tracking-widest text-center text-sm"
                />
              </div>

              <div>
                <label className="block text-[#8e8ea0] mb-1 font-medium">Select Product to Claim</label>
                <select
                  value={selectedProduct}
                  onChange={(e) => setSelectedProduct(e.target.value)}
                  className="w-full p-2.5 bg-[#212121] border border-white/10 rounded-xl text-[#ececec] focus:outline-none focus:border-white/15"
                >
                  <option value="Gemini Advanced">Gemini Advanced (1-Year Invite Link)</option>
                  <option value="Claude Pro">Claude Pro (Private Org Invite)</option>
                  <option value="ChatGPT Plus">ChatGPT Plus (1-Month Workspace)</option>
                  <option value="Canva Pro">Canva Pro (Lifetime Edu Invite)</option>
                  <option value="Office 365">Office 365 (5-Device Enterprise)</option>
                </select>
              </div>

              <div className="p-2.5 bg-[#2f2f2f] border border-white/15 rounded-xl text-[11px] text-[#ececec]">
                💡 Product ka reseller price aapke wallet se automatically katega, aur single-use link turant chat me milega.
              </div>

              <button
                type="submit"
                className="w-full py-2.5 bg-gradient-to-r from-white to-white hover:from-white hover:to-white text-black font-bold rounded-xl transition-all shadow-md"
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
