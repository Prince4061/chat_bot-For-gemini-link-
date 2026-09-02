import React, { useState } from 'react';
import { 
  Bot, 
  User, 
  Copy, 
  Check, 
  ExternalLink, 
  QrCode, 
  Flame, 
  ListTodo, 
  CheckCircle2, 
  Clock, 
  ShieldAlert,
  Sparkles
} from 'lucide-react';
import confetti from 'canvas-confetti';

export default function MessageItem({ message, onOpenPaymentQr }) {
  const isUser = message.role === 'user';
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedText, setCopiedText] = useState(false);

  // Extract invite links from text (e.g. https://... or token=... or KEY-...)
  const linkRegex = /(https?:\/\/[^\s`]+|token=[^\s`]+)/gi;
  const foundLinks = message.content ? message.content.match(linkRegex) : null;
  const isClaimSuccess = message.content && (
    message.content.includes('Link Claimed & Burned') || 
    message.content.includes('Single-Use Invite Link') ||
    message.content.includes('Payment confirmed')
  );

  const handleCopyLink = (link) => {
    navigator.clipboard.writeText(link);
    setCopiedLink(true);
    confetti({
      particleCount: 60,
      spread: 60,
      origin: { y: 0.7 }
    });
    setTimeout(() => setCopiedLink(false), 2500);
  };

  const handleCopyFull = () => {
    navigator.clipboard.writeText(message.content);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  // Render markdown-like simple text formatting
  const renderFormattedContent = (text) => {
    if (!text) return null;

    const lines = text.split('\n');
    return lines.map((line, idx) => {
      // Bold formatting
      let formatted = line;
      
      // Header detection
      if (line.startsWith('### ')) {
        return <h3 key={idx} className="text-sm font-bold text-slate-100 mt-2 mb-1">{line.replace('### ', '')}</h3>;
      }
      if (line.startsWith('## ')) {
        return <h2 key={idx} className="text-base font-bold text-emerald-400 mt-3 mb-1.5">{line.replace('## ', '')}</h2>;
      }
      if (line.startsWith('• ') || line.startsWith('- ')) {
        return (
          <div key={idx} className="flex items-start gap-2 my-1 text-slate-300 pl-2">
            <span className="text-emerald-400 font-bold">•</span>
            <span dangerouslySetInnerHTML={{ __html: formatInline(line.substring(2)) }} />
          </div>
        );
      }

      if (line.trim() === '') {
        return <div key={idx} className="h-2"></div>;
      }

      return (
        <p key={idx} className="my-1 text-slate-200 leading-relaxed" dangerouslySetInnerHTML={{ __html: formatInline(formatted) }} />
      );
    });
  };

  const formatInline = (str) => {
    return str
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-emerald-300">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em class="text-slate-300 italic">$1</em>')
      .replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-slate-800 text-emerald-400 font-mono text-xs border border-slate-700">$1</code>');
  };

  // Extract todos metadata if present
  const todos = message.metadata?.todos || [];

  return (
    <div className={`flex gap-3.5 max-w-4xl mx-auto px-4 py-3 group ${isUser ? 'justify-end' : 'justify-start'}`}>
      {/* Bot Avatar */}
      {!isUser && (
        <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center shrink-0 shadow-md shadow-emerald-950/40 mt-1">
          <Bot className="w-4 h-4 text-slate-950" />
        </div>
      )}

      {/* Message Bubble */}
      <div className={`max-w-[85%] rounded-2xl p-4 transition-all ${
        isUser
          ? 'bg-gradient-to-br from-emerald-700 to-teal-800 text-white shadow-lg shadow-emerald-950/30'
          : 'glass-panel text-slate-200 shadow-lg shadow-black/40'
      }`}>
        
        {/* Deep Agent Todo Plan Box (if agent executed multi-step planning) */}
        {!isUser && todos && todos.length > 0 && (
          <div className="mb-3.5 p-3 rounded-xl bg-slate-900/90 border border-slate-800 text-xs">
            <div className="flex items-center gap-1.5 text-slate-400 font-semibold mb-2">
              <ListTodo className="w-3.5 h-3.5 text-emerald-400" />
              <span>Deep Agent Execution Plan</span>
            </div>
            <div className="space-y-1.5">
              {todos.map((todo, tIdx) => (
                <div key={tIdx} className="flex items-center gap-2">
                  {todo.status === 'completed' ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  ) : (
                    <Clock className="w-3.5 h-3.5 text-amber-400 shrink-0 animate-pulse" />
                  )}
                  <span className={todo.status === 'completed' ? 'text-slate-300 line-through' : 'text-slate-200 font-medium'}>
                    {todo.task}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Message Content Body */}
        <div className="text-sm">
          {renderFormattedContent(message.content)}
        </div>

        {/* Single-Use Link Special Highlight Card */}
        {!isUser && isClaimSuccess && foundLinks && foundLinks.length > 0 && (
          <div className="mt-4 p-3.5 rounded-xl bg-gradient-to-br from-slate-900 to-emerald-950/60 border border-emerald-500/40 shadow-xl">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-1.5 text-emerald-400 font-bold text-xs uppercase tracking-wide">
                <Flame className="w-4 h-4 text-emerald-400 animate-bounce" />
                <span>Single-Use Link Burned & Claimed</span>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium">
                1-Time Access
              </span>
            </div>

            {foundLinks.map((link, lIdx) => (
              <div key={lIdx} className="p-2.5 bg-slate-950/90 rounded-lg border border-slate-800 flex items-center justify-between gap-2 my-1">
                <code className="text-xs text-emerald-300 truncate font-mono select-all">
                  {link}
                </code>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => handleCopyLink(link)}
                    className="flex items-center gap-1 px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-semibold rounded-md text-xs transition-all active:scale-95 shadow-sm"
                    title="Copy Link"
                  >
                    {copiedLink ? <Check className="w-3 h-3 text-slate-950" /> : <Copy className="w-3 h-3 text-slate-950" />}
                    {copiedLink ? 'Copied!' : 'Copy'}
                  </button>
                  {link.startsWith('http') && (
                    <a
                      href={link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-md transition-colors"
                      title="Open in new tab"
                    >
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>
            ))}

            <p className="text-[11px] text-slate-400 mt-2 flex items-center gap-1">
              <ShieldAlert className="w-3 h-3 text-emerald-400" />
              This link is permanently locked to your account and cannot be redistributed.
            </p>
          </div>
        )}

        {/* Dynamic UPI Payment Button if order or UPI is mentioned */}
        {!isUser && (message.content?.includes('UPI ID') || message.content?.includes('resellerpay@upi') || message.content?.includes('Payment Instructions')) && (
          <div className="mt-3 pt-2.5 border-t border-slate-800 flex items-center gap-2">
            <button
              onClick={onOpenPaymentQr}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 hover:text-emerald-300 font-semibold text-xs rounded-lg border border-slate-700/80 transition-all shadow-sm"
            >
              <QrCode className="w-3.5 h-3.5 text-emerald-400" />
              Show UPI QR Code
            </button>
            <span className="text-[11px] text-slate-400">
              Instant scan & pay via any UPI app
            </span>
          </div>
        )}

        {/* Message Action Utilities (Copy) */}
        {!isUser && (
          <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400 pt-1.5 border-t border-slate-800/40">
            <span className="text-[10px] text-slate-400">
              Deep Agent 2.0
            </span>
            <button
              onClick={handleCopyFull}
              className="flex items-center gap-1 hover:text-slate-300 transition-colors"
              title="Copy message text"
            >
              {copiedText ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              <span>{copiedText ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
        )}
      </div>

      {/* User Avatar */}
      {isUser && (
        <div className="w-8 h-8 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 shadow-md mt-1">
          <User className="w-4 h-4 text-emerald-400" />
        </div>
      )}
    </div>
  );
}
