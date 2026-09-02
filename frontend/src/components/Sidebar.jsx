import React from 'react';
import {
  PenSquare,
  Trash2,
  MessageSquare,
  KeyRound,
  LayoutGrid,
  X
} from 'lucide-react';

export default function Sidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  activeView,
  setActiveView,
  onClose
}) {
  return (
    <aside className="w-[80vw] max-w-xs md:w-64 bg-[#171717] flex flex-col h-full select-none shrink-0 text-[#ececec]">

      {/* Header: brand + close (mobile) */}
      <div className="p-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-white flex items-center justify-center text-black font-bold text-sm">
            V
          </div>
          <span className="font-medium text-sm">Vending</span>
        </div>
        <button
          onClick={onClose}
          className="md:hidden p-2 -mr-1 text-[#b4b4b4] hover:text-white rounded-lg hover:bg-[#2f2f2f]"
          aria-label="Close menu"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* New chat */}
      <div className="px-2 pb-2">
        <button
          onClick={onNewSession}
          className="w-full flex items-center gap-2.5 py-2.5 px-3 rounded-lg hover:bg-[#2f2f2f] text-[#ececec] text-sm font-medium transition-colors"
        >
          <PenSquare className="w-4 h-4" />
          New chat
        </button>
      </div>

      {/* Conversation history */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        <div className="px-3 pb-1 text-[11px] font-medium text-[#8e8ea0]">
          Chats
        </div>

        {sessions.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-[#8e8ea0]">
            No chats yet
          </div>
        ) : (
          sessions.map((s) => {
            const isActive = s.id === activeSessionId && activeView === 'chat';
            return (
              <div
                key={s.id}
                onClick={() => { onSelectSession(s.id); setActiveView('chat'); }}
                className={`group flex items-center gap-2.5 pl-3 pr-2 py-2 rounded-lg text-sm cursor-pointer transition-colors ${
                  isActive ? 'bg-[#2f2f2f] text-[#ececec]' : 'text-[#ececec] hover:bg-[#2f2f2f]'
                }`}
              >
                {s.user_type === 'reseller'
                  ? <KeyRound className="w-4 h-4 text-[#8e8ea0] shrink-0" />
                  : <MessageSquare className="w-4 h-4 text-[#8e8ea0] shrink-0" />}
                <span className="truncate flex-1">{s.title || 'New chat'}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id); }}
                  className="opacity-0 group-hover:opacity-100 md:opacity-0 p-1 text-[#8e8ea0] hover:text-rose-400 transition-opacity shrink-0"
                  aria-label="Delete chat"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Footer: admin access */}
      <div className="p-2 border-t border-white/5">
        <button
          onClick={() => setActiveView(activeView === 'admin' ? 'chat' : 'admin')}
          className={`w-full flex items-center gap-2.5 py-2.5 px-3 rounded-lg text-sm font-medium transition-colors ${
            activeView === 'admin' ? 'bg-[#2f2f2f] text-[#ececec]' : 'text-[#ececec] hover:bg-[#2f2f2f]'
          }`}
        >
          <LayoutGrid className="w-4 h-4 text-[#b4b4b4]" />
          {activeView === 'admin' ? 'Back to chat' : 'Admin'}
        </button>
      </div>
    </aside>
  );
}
