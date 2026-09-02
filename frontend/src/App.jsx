import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatView from './components/ChatView';
import AdminDashboard from './components/AdminDashboard';
import { chatApi } from './api/client';

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeView, setActiveView] = useState('chat'); // 'chat' or 'admin'
  const [sidebarOpen, setSidebarOpen] = useState(false); // mobile drawer
  // No manual persona: the assistant asks whether the user is a customer or reseller,
  // and the backend promotes the session to 'reseller' once a passcode is verified.
  const userType = 'customer';

  // Load chat sessions on startup
  const fetchSessions = async () => {
    try {
      const data = await chatApi.getSessions();
      setSessions(data);
      if (data.length > 0 && !activeSessionId) {
        setActiveSessionId(data[0].id);
        fetchHistory(data[0].id);
      } else if (data.length === 0) {
        handleNewSession();
      }
    } catch (err) {
      console.error('Failed to load chat sessions:', err);
    }
  };

  const fetchHistory = async (sessionId) => {
    try {
      const data = await chatApi.getHistory(sessionId);
      setMessages(data.messages || []);
    } catch (err) {
      console.error('Failed to load history:', err);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handleSelectSession = (sessionId) => {
    setActiveSessionId(sessionId);
    fetchHistory(sessionId);
    setSidebarOpen(false); // close drawer on mobile after picking a chat
  };

  const handleNewSession = async () => {
    try {
      const newSess = await chatApi.newSession(userType);
      setSessions([newSess, ...sessions]);
      setActiveSessionId(newSess.id);
      setMessages([]);
      setActiveView('chat');
      setSidebarOpen(false);
    } catch (err) {
      console.error('Failed to create new session:', err);
    }
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await chatApi.deleteSession(sessionId);
      const remaining = sessions.filter(s => s.id !== sessionId);
      setSessions(remaining);
      if (activeSessionId === sessionId) {
        if (remaining.length > 0) {
          setActiveSessionId(remaining[0].id);
          fetchHistory(remaining[0].id);
        } else {
          handleNewSession();
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

  const handleSendMessage = async (text) => {
    if (!text.trim()) return;

    let currentSessId = activeSessionId;
    if (!currentSessId) {
      currentSessId = `chat_${Date.now()}`;
      setActiveSessionId(currentSessId);
    }

    // Optimistically add user message
    const userMsgObj = {
      role: 'user',
      content: text,
      metadata: {}
    };
    setMessages(prev => [...prev, userMsgObj]);
    setLoading(true);

    try {
      const response = await chatApi.sendMessage(
        currentSessId,
        text,
        userType
      );

      // Add bot response
      const botMsgObj = {
        role: 'assistant',
        content: response.message,
        metadata: response.metadata || { todos: response.todos, files: response.files }
      };

      setMessages(prev => [...prev, botMsgObj]);
      fetchSessions(); // update session list titles
    } catch (err) {
      console.error('Error sending message:', err);
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: '⚠️ Failed to connect to Deep Agent backend. Please ensure the Flask server is running.',
          metadata: {}
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[100dvh] bg-[#212121] font-sans text-[#ececec] overflow-hidden">
      {/* Mobile backdrop when the drawer is open */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
        />
      )}

      {/* Sidebar: static on desktop, slide-in drawer on mobile */}
      <div
        className={`fixed z-40 h-[100dvh] md:static md:z-auto md:translate-x-0 transition-transform duration-300 ease-out ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Sidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
          activeView={activeView}
          setActiveView={setActiveView}
          onClose={() => setSidebarOpen(false)}
        />
      </div>

      {/* Main View Area */}
      {activeView === 'chat' ? (
        <ChatView
          messages={messages}
          onSendMessage={handleSendMessage}
          loading={loading}
          currentSessionId={activeSessionId}
          onOpenSidebar={() => setSidebarOpen(true)}
          onNewSession={handleNewSession}
        />
      ) : (
        <AdminDashboard
          onSwitchToChat={() => setActiveView('chat')}
          onOpenSidebar={() => setSidebarOpen(true)}
        />
      )}
    </div>
  );
}
