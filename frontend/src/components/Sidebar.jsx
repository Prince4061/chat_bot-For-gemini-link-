import React from 'react';
import { 
  MessageSquarePlus, 
  Bot, 
  ShieldCheck, 
  User, 
  KeyRound, 
  Trash2, 
  Sparkles,
  Zap,
  LayoutDashboard,
  MessageSquare
} from 'lucide-react';

export default function Sidebar({ 
  sessions, 
  activeSessionId, 
  onSelectSession, 
  onNewSession, 
  onDeleteSession,
  activeView, 
  setActiveView,
  userType,
  setUserType
}) {
  return (
    <aside className="w-72 bg-slate-950 border-r border-slate-800/80 flex flex-col h-screen select-none shrink-0 transition-all duration-300">
      {/* Brand Header */}
      <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-950/50">
            <Sparkles className="w-5 h-5 text-slate-950 font-bold" />
          </div>
          <div>
            <h1 className="font-bold text-sm text-slate-100 tracking-tight leading-tight">Digital Vending</h1>
            <p className="text-[11px] text-emerald-400 font-medium flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Deep Agent 2.0
            </p>
          </div>
        </div>
      </div>

      {/* Main Mode Toggle Buttons */}
      <div className="p-3 border-b border-slate-800/60 space-y-2">
        <button
          onClick={onNewSession}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-3 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-slate-950 font-semibold text-xs rounded-xl shadow-md shadow-emerald-950/40 transition-all duration-200 active:scale-[0.98]"
        >
          <MessageSquarePlus className="w-4 h-4 text-slate-950" />
          New Conversation
        </button>

        {/* View Switcher: Chat vs Admin */}
        <div className="grid grid-cols-2 gap-1.5 p-1 bg-slate-900 rounded-xl border border-slate-800">
          <button
            onClick={() => setActiveView('chat')}
            className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-xs font-medium transition-all ${
              activeView === 'chat'
                ? 'bg-slate-800 text-emerald-400 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            AI Chat
          </button>
          <button
            onClick={() => setActiveView('admin')}
            className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-xs font-medium transition-all ${
              activeView === 'admin'
                ? 'bg-slate-800 text-teal-400 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <LayoutDashboard className="w-3.5 h-3.5" />
            Admin Panel
          </button>
        </div>

        {/* Role Persona Switcher (Customer vs Reseller) */}
        {activeView === 'chat' && (
          <div className="pt-1">
            <label className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block mb-1 px-1">
              Active Persona
            </label>
            <div className="grid grid-cols-2 gap-1.5 p-1 bg-slate-900/90 rounded-xl border border-slate-800/80">
              <button
                onClick={() => setUserType('customer')}
                className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-xs font-medium transition-all ${
                  userType === 'customer'
                    ? 'bg-emerald-950/80 border border-emerald-500/40 text-emerald-300'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <User className="w-3.5 h-3.5" />
                Customer
              </button>
              <button
                onClick={() => setUserType('reseller')}
                className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-xs font-medium transition-all ${
                  userType === 'reseller'
                    ? 'bg-teal-950/80 border border-teal-500/40 text-teal-300'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <KeyRound className="w-3.5 h-3.5" />
                Reseller
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Conversations History List */}
      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
        <div className="px-2 pb-1.5 flex items-center justify-between text-[11px] font-semibold text-slate-400">
          <span>Recent Conversations</span>
          <span className="text-[10px] bg-slate-800/80 text-slate-400 px-1.5 py-0.5 rounded-full">
            {sessions.length}
          </span>
        </div>

        {sessions.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-400 italic">
            No past conversations yet
          </div>
        ) : (
          sessions.map((s) => {
            const isActive = s.id === activeSessionId && activeView === 'chat';
            return (
              <div
                key={s.id}
                onClick={() => {
                  onSelectSession(s.id);
                  setActiveView('chat');
                }}
                className={`group flex items-center justify-between p-2 rounded-xl text-xs cursor-pointer transition-all ${
                  isActive
                    ? 'bg-slate-800/90 text-slate-100 border border-slate-700 shadow-sm'
                    : 'text-slate-400 hover:bg-slate-900/60 hover:text-slate-200'
                }`}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  {s.user_type === 'reseller' ? (
                    <KeyRound className="w-3.5 h-3.5 text-teal-400 shrink-0" />
                  ) : (
                    <Bot className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  )}
                  <span className="truncate max-w-[150px] font-normal">
                    {s.title || 'Conversation'}
                  </span>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 text-slate-400 transition-opacity"
                  title="Delete conversation"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/60 flex items-center justify-between text-[11px] text-slate-400">
        <div className="flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-emerald-400" />
          <span>OpenAI & LangGraph</span>
        </div>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400 font-mono">
          v2.0
        </span>
      </div>
    </aside>
  );
}
