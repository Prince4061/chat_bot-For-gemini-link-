import React, { useState } from 'react';
import { Copy, Check, ExternalLink, ListTodo, CheckCircle2, Clock, Sparkles } from 'lucide-react';
import confetti from 'canvas-confetti';

export default function MessageItem({ message, onOpenPaymentQr }) {
  const isUser = message.role === 'user';
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedText, setCopiedText] = useState(false);

  const linkRegex = /(https?:\/\/[^\s`]+|token=[^\s`]+)/gi;
  const foundLinks = message.content ? message.content.match(linkRegex) : null;
  const isClaimSuccess = message.content && (
    message.content.includes('Link Claimed & Burned') ||
    message.content.includes('Single-Use Invite Link') ||
    message.content.includes('single-use') ||
    message.content.includes('Payment confirmed')
  );

  const handleCopyLink = (link) => {
    navigator.clipboard.writeText(link);
    setCopiedLink(true);
    confetti({ particleCount: 50, spread: 55, origin: { y: 0.7 } });
    setTimeout(() => setCopiedLink(false), 2200);
  };

  const handleCopyFull = () => {
    navigator.clipboard.writeText(message.content);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 1800);
  };

  const formatInline = (str) =>
    str
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-white">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em class="italic text-[#b4b4b4]">$1</em>')
      .replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-black/30 text-[#ececec] font-mono text-[13px]">$1</code>');

  const renderFormattedContent = (text) => {
    if (!text) return null;
    return text.split('\n').map((line, idx) => {
      if (line.startsWith('### ')) return <h3 key={idx} className="text-sm font-semibold text-[#ececec] mt-2 mb-1">{line.replace('### ', '')}</h3>;
      if (line.startsWith('## ')) return <h2 key={idx} className="text-base font-semibold text-[#ececec] mt-3 mb-1.5">{line.replace('## ', '')}</h2>;
      if (line.startsWith('• ') || line.startsWith('- ')) {
        return (
          <div key={idx} className="flex items-start gap-2 my-1 text-[#ececec] pl-1">
            <span className="text-[#8e8ea0] mt-0.5">•</span>
            <span dangerouslySetInnerHTML={{ __html: formatInline(line.substring(2)) }} />
          </div>
        );
      }
      if (line.trim() === '') return <div key={idx} className="h-2" />;
      return <p key={idx} className="my-1 text-[#ececec] leading-7" dangerouslySetInnerHTML={{ __html: formatInline(line) }} />;
    });
  };

  const todos = message.metadata?.todos || [];

  // --- User message: right-aligned grey bubble (ChatGPT style) ---
  if (isUser) {
    return (
      <div className="w-full max-w-3xl mx-auto px-3 py-2 flex justify-end">
        <div className="max-w-[85%] rounded-3xl px-4 py-2.5 bg-[#2f2f2f] text-[#ececec] text-sm leading-relaxed whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    );
  }

  // --- Assistant message: avatar + borderless content ---
  return (
    <div className="w-full max-w-3xl mx-auto px-3 py-2 flex gap-3">
      <div className="w-7 h-7 rounded-full bg-white flex items-center justify-center shrink-0 mt-0.5">
        <Sparkles className="w-3.5 h-3.5 text-black" />
      </div>

      <div className="flex-1 min-w-0 text-sm">
        {/* Deep Agent plan (only when present) */}
        {todos.length > 0 && (
          <div className="mb-3 p-3 rounded-xl bg-[#2f2f2f] text-xs">
            <div className="flex items-center gap-1.5 text-[#b4b4b4] font-medium mb-2">
              <ListTodo className="w-3.5 h-3.5" />
              <span>Plan</span>
            </div>
            <div className="space-y-1.5">
              {todos.map((todo, tIdx) => (
                <div key={tIdx} className="flex items-center gap-2">
                  {todo.status === 'completed'
                    ? <CheckCircle2 className="w-3.5 h-3.5 text-[#ececec] shrink-0" />
                    : <Clock className="w-3.5 h-3.5 text-[#8e8ea0] shrink-0" />}
                  <span className={todo.status === 'completed' ? 'text-[#8e8ea0] line-through' : 'text-[#ececec]'}>
                    {todo.task}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Body */}
        <div>{renderFormattedContent(message.content)}</div>

        {/* Single-use link highlight */}
        {isClaimSuccess && foundLinks && foundLinks.length > 0 && (
          <div className="mt-3 p-3 rounded-xl bg-[#2f2f2f] border border-white/10">
            <div className="text-[11px] uppercase tracking-wide text-[#8e8ea0] font-medium mb-2">
              Single-use link
            </div>
            {foundLinks.map((link, lIdx) => (
              <div key={lIdx} className="p-2.5 bg-black/30 rounded-lg flex items-center justify-between gap-2 my-1">
                <code className="text-xs text-[#ececec] truncate font-mono select-all">{link}</code>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => handleCopyLink(link)}
                    className="flex items-center gap-1 px-2.5 py-1.5 bg-white hover:bg-white/90 text-black font-medium rounded-md text-xs transition-colors"
                    title="Copy link"
                  >
                    {copiedLink ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    {copiedLink ? 'Copied' : 'Copy'}
                  </button>
                  {link.startsWith('http') && (
                    <a href={link} target="_blank" rel="noopener noreferrer" className="p-1.5 bg-white/10 hover:bg-white/20 text-[#ececec] rounded-md transition-colors" title="Open">
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* UPI pay shortcut */}
        {(message.content?.includes('UPI ID') || message.content?.includes('Payment Instructions') || message.content?.includes('UPI:')) && (
          <div className="mt-2">
            <button
              onClick={onOpenPaymentQr}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#2f2f2f] hover:bg-[#3a3a3a] text-[#ececec] font-medium text-xs rounded-lg transition-colors"
            >
              Show UPI QR
            </button>
          </div>
        )}

        {/* Copy action */}
        <div className="mt-2 flex items-center text-[11px] text-[#8e8ea0]">
          <button onClick={handleCopyFull} className="flex items-center gap-1 hover:text-[#ececec] transition-colors" title="Copy">
            {copiedText ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            <span>{copiedText ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
