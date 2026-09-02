import React, { useState } from 'react';
import { X, Copy, Check, QrCode, ShieldCheck, ArrowRight } from 'lucide-react';

export default function PaymentModal({ isOpen, onClose, upiId = 'resellerpay@upi', payeeName = 'Digital Vending Admin' }) {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(upiId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-md bg-[#2f2f2f] border border-white/15 rounded-2xl shadow-2xl p-6 text-[#ececec]">
        
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 rounded-lg text-[#8e8ea0] hover:text-[#ececec] hover:bg-[#3a3a3a] transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="text-center mb-5">
          <div className="w-12 h-12 mx-auto mb-2 rounded-2xl bg-[#2f2f2f] border border-white/15 flex items-center justify-center text-[#ececec]">
            <QrCode className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-[#ececec]">Scan & Pay via UPI</h2>
          <p className="text-xs text-[#8e8ea0]">Instant Verification & Single-Use Link Delivery</p>
        </div>

        {/* QR Image Container */}
        <div className="p-4 bg-[#212121] rounded-xl border border-white/10 flex flex-col items-center justify-center mb-4">
          <div className="p-2 bg-[#2f2f2f] rounded-lg border border-white/10">
            <img
              src="/api/qr/upi"
              alt="UPI Payment QR Code"
              className="w-48 h-48 rounded object-contain"
            />
          </div>
          <p className="text-[11px] text-[#ececec] mt-2 font-medium flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5" />
            Verified Merchant Account
          </p>
        </div>

        {/* UPI Details Box */}
        <div className="space-y-2 mb-4">
          <div className="p-2.5 bg-[#3a3a3a]/80 rounded-xl border border-white/15 flex items-center justify-between">
            <div>
              <span className="text-[10px] uppercase font-bold text-[#8e8ea0] block">UPI ID</span>
              <span className="text-xs font-mono font-semibold text-[#ececec]">{upiId}</span>
            </div>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-3 py-1.5 bg-white hover:bg-white/90 text-black font-bold text-xs rounded-lg transition-all"
            >
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>

          <div className="p-2.5 bg-[#3a3a3a]/40 rounded-xl border border-white/10 text-xs flex justify-between">
            <span className="text-[#8e8ea0]">Payee Name:</span>
            <span className="font-medium text-[#ececec]">{payeeName}</span>
          </div>
        </div>

        {/* Instructions */}
        <div className="p-3 bg-[#2f2f2f] border border-white/15 rounded-xl text-xs text-[#d4d4d4] space-y-1">
          <p className="font-semibold text-[#ececec] flex items-center gap-1">
            <ArrowRight className="w-3 h-3 text-[#ececec]" />
            Next Step after Payment:
          </p>
          <p className="text-[11px] text-[#8e8ea0]">
            Copy your 12-digit UTR / Payment Transaction ID from GPay/PhonePe and paste it in the chat to instantly unlock your private invite link.
          </p>
        </div>

        <button
          onClick={onClose}
          className="w-full mt-4 py-2 bg-[#3a3a3a] hover:bg-[#4a4a4a] text-[#ececec] font-semibold rounded-xl text-xs transition-colors"
        >
          Close Window
        </button>
      </div>
    </div>
  );
}
