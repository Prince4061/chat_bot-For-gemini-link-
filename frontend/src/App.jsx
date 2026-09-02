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
  const [userType, setUserType] = useState('customer'); // 'customer' or 'reseller'

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
      if (data.session?.user_type) {
        setUserType(data.session.user_type);
      }
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
  };

  const handleNewSession = async () => {
    try {
      const newSess = await chatApi.newSession(userType);
      setSessions([newSess, ...sessions]);
      setActiveSessionId(newSess.id);
      setMessages([]);
      setActiveView('chat');
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
    <div className="flex h-screen bg-slate-950 font-sans text-slate-100 overflow-hidden">
      {/* ChatGPT-style Left Sidebar */}
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
        activeView={activeView}
        setActiveView={setActiveView}
        userType={userType}
        setUserType={setUserType}
      />

      {/* Main View Area */}
      {activeView === 'chat' ? (
        <ChatView
          messages={messages}
          onSendMessage={handleSendMessage}
          loading={loading}
          userType={userType}
          setUserType={setUserType}
          currentSessionId={activeSessionId}
        />
      ) : (
        <AdminDashboard
          onSwitchToChat={() => setActiveView('chat')}
        />
      )}
    </div>
  );
}
