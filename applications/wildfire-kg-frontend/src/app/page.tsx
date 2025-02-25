'use client';

import { useState } from 'react';

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
}

export default function HomePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputText,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputText('');

    // TODO: Add actual API call here
    // Simulate assistant response
    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      text: 'This is a placeholder response. The actual implementation will connect to your knowledge graph backend.',
      sender: 'assistant',
      timestamp: new Date(),
    };

    setTimeout(() => {
      setMessages(prev => [...prev, assistantMessage]);
    }, 1000);
  };

  return (
    <div className="max-w-4xl mx-auto p-4 h-[calc(100vh-theme(spacing.32))]">
      <div className="flex flex-col h-full">
        <div className="flex-grow overflow-y-auto mb-4 p-4 bg-white rounded-lg shadow">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`mb-4 ${
                message.sender === 'user' ? 'text-right' : 'text-left'
              }`}
            >
              <div
                className={`inline-block p-3 rounded-lg ${
                  message.sender === 'user'
                    ? 'bg-[#03619B] text-white'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                {message.text}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {message.timestamp.toLocaleTimeString()}
              </div>
            </div>
          ))}
          {messages.length === 0 && (
            <div className="text-center text-gray-500 mt-8">
              Start a conversation about the knowledge graph...
            </div>
          )}
        </div>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Ask about the knowledge graph..."
            className="flex-grow p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#03619B]"
          />
          <button
            type="submit"
            className="bg-[#03619B] text-white px-4 py-2 rounded-lg hover:bg-[#03619B]/90 transition-colors"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
