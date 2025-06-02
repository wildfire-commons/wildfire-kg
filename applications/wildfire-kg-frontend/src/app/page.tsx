'use client';

import { useState } from 'react';
import { generateId } from '@/utils/id';
import { Message } from '@/types/chat';

const GRAPH_NAME = 'wildfire-kg';

interface ChatContext {
  kg_results?: any;
  rag_results?: any;
  weather_results?: any;
}

interface ExtendedMessage extends Message {
  content?: string;
  text: string;
  type?: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ExtendedMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [context, setContext] = useState<ChatContext | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [showReasoning, setShowReasoning] = useState(false);
  const [pendingUserMessage, setPendingUserMessage] = useState<ExtendedMessage | null>(null);

  function splitMessages(messages: any[], pendingMsg: any) {
    // Insert pending user message if present and not already in messages
    let allMessages = messages;
    if (pendingMsg && !messages.some(m => m.content === pendingMsg.content && m.sender === 'user')) {
      allMessages = [pendingMsg, ...messages];
    }
    const filtered = allMessages.filter(
      (msg, idx, arr) =>
        (msg.type === 'human' || msg.sender === 'user') ||
        (msg.content && msg.content.trim() !== '') &&
        // Deduplicate by content and sender
        arr.findIndex(m => m.content === msg.content && m.sender === msg.sender) === idx
    );
    let finalIdx = -1;
    for (let i = filtered.length - 1; i >= 0; i--) {
      const msg = filtered[i];
      if ((msg.type === "ai" || msg.type === "tool" || msg.sender === "assistant") && msg.content && msg.content.trim() !== "") {
        finalIdx = i;
        break;
      }
    }
    if (finalIdx === -1) return { reasoning: filtered, final: null };
    return {
      reasoning: filtered.slice(0, finalIdx),
      final: filtered[finalIdx]
    };
  }

  const createThread = async (userInput: string) => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/threads`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          initial_message: userInput
        })
      });
      if (!response.ok) throw new Error('Failed to create thread');
      const data = await response.json();
      setThreadId(data.thread_id);
      if (data.messages) {
        setMessages(prev => {
          // Remove any pending user message with same content
          return [
            ...prev.filter((msg) => msg.sender === 'user' && msg.content !== userInput),
            ...data.messages
          ];
        });
      }
      if (data.kg_results || data.rag_results || data.weather_results) {
        setContext({
          kg_results: data.kg_results,
          rag_results: data.rag_results,
          weather_results: data.weather_results
        });
      }
      return data.thread_id;
    } catch (error) {
      console.error('Failed to create thread:', error);
      return null;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    const userMessage: ExtendedMessage = {
      id: generateId(),
      content: input,
      text: input,
      sender: 'user',
      type: 'human',
      timestamp: new Date(),
    };
    setPendingUserMessage(userMessage);
    setInput('');
    setLoading(true);
    try {
      let backendMessages: any[] = [];
      if (!threadId) {
        const newThreadId = await createThread(input);
        setThreadId(newThreadId);
        setPendingUserMessage(null);
        setLoading(false);
        return;
      } else {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/threads/${threadId}/runs`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            assistant_id: GRAPH_NAME,
            input: {
              user_query: input,
              history: messages.map((msg) => ({
                id: msg.id,
                text: msg.content || msg.text,
                sender: msg.sender,
                timestamp: msg.timestamp?.toISOString?.() || ''
              }))
            }
          }),
        });
        if (!response.ok) throw new Error('Failed to get response');
        const data = await response.json();
        backendMessages = data.messages || [];
        setMessages((prev) => {
          // Remove any pending user message with same content
          return [
            ...prev.filter((msg) => msg.sender === 'user' && msg.content !== input),
            ...backendMessages
          ];
        });
        setPendingUserMessage(null);
        if (data.kg_results || data.rag_results || data.weather_results) {
          setContext({
            kg_results: data.kg_results,
            rag_results: data.rag_results,
            weather_results: data.weather_results
          });
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      setMessages((prev) => {
        const newMessages = [...prev];
        const lastMessage = newMessages[newMessages.length - 1];
        if (lastMessage && lastMessage.sender === 'assistant') {
          lastMessage.content = 'Sorry, I encountered an error. Please try again.';
        }
        return newMessages;
      });
      setPendingUserMessage(null);
    } finally {
      setLoading(false);
    }
  };

  const { reasoning, final } = splitMessages(messages, pendingUserMessage);
  // Extract all user messages for chat bubbles, ordered chronologically
  const userMessages = [
    ...messages.filter((msg) => msg.sender === 'user' || msg.type === 'human'),
    ...(pendingUserMessage ? [pendingUserMessage] : [])
  ]
    .filter((msg, idx, arr) => arr.findIndex(m => m.content === msg.content && m.sender === msg.sender) === idx)
    .sort((a, b) => {
      const aTime = a.timestamp ? new Date(a.timestamp).getTime() : 0;
      const bTime = b.timestamp ? new Date(b.timestamp).getTime() : 0;
      return aTime - bTime;
    });

  return (
    <div className="max-w-4xl mx-auto p-4">
      <div className="flex flex-col h-[calc(100vh-8rem)]">
        <div className="flex-1 overflow-y-auto mb-4 space-y-4">
          {/* User chat bubbles */}
          {userMessages.map((msg) => (
            <div key={msg.id} className="flex justify-end">
              <div
                style={{ whiteSpace: 'pre-line' }}
                className="max-w-[80%] rounded-lg p-4 bg-blue-600 text-white"
              >
                <p>{msg.content}</p>
                <p className="text-xs mt-2 opacity-70">{msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}</p>
              </div>
            </div>
          ))}
          {/* Final Answer */}
          {final && (
            <div
              style={{ whiteSpace: 'pre-line' }}
              className="bg-green-50 p-4 rounded mb-2"
            >
              <div>{final.content || <em>[no content]</em>}</div>
              <p className="text-xs mt-2 opacity-70">{final.timestamp ? new Date(final.timestamp).toLocaleTimeString() : ''}</p>
            </div>
          )}
          {/* Reasoning Steps (expandable) */}
          {reasoning.length > 0 && (
            <div className="mb-2">
              <button
                className="text-gray-500 underline mb-2"
                onClick={() => setShowReasoning((v) => !v)}
              >
                {showReasoning ? "Hide Reasoning Steps" : "Show Reasoning Steps"}
              </button>
              {showReasoning && (
                <div className="bg-gray-50 p-4 rounded">
                  <strong className="block mb-2">Reasoning Steps:</strong>
                  <ul className="list-disc ml-6 text-sm text-gray-600">
                    {reasoning.map((msg, idx) => (
                      <li key={msg.id || idx} className="text-gray-500 text-xs">
                        <span className="font-mono text-xs text-gray-400">{msg.type || msg.sender}</span>: {msg.content || <em>[no content]</em>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-lg p-4">
                <div className="flex space-x-2">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
                </div>
              </div>
            </div>
          )}
        </div>
        {context && (
          <div className="mb-4 p-4 bg-blue-50 rounded-lg">
            <h3 className="font-semibold mb-2">Results:</h3>
            <div className="text-sm space-y-2">
              {context.kg_results && (
                <div>
                  <h4 className="font-medium">Knowledge Graph Results:</h4>
                  <pre className="bg-white p-2 rounded mt-1 overflow-x-auto">
                    {JSON.stringify(context.kg_results, null, 2)}
                  </pre>
                </div>
              )}
              {context.rag_results && (
                <div>
                  <h4 className="font-medium">RAG Results:</h4>
                  <pre className="bg-white p-2 rounded mt-1 overflow-x-auto">
                    {JSON.stringify(context.rag_results, null, 2)}
                  </pre>
                </div>
              )}
              {context.weather_results && (
                <div>
                  <h4 className="font-medium">Weather Results:</h4>
                  <pre className="bg-white p-2 rounded mt-1 overflow-x-auto">
                    {JSON.stringify(context.weather_results, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about prescribed burns and wildfires..."
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-[#03619B]"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-[#03619B] text-white px-4 py-2 rounded-lg hover:bg-[#03619B]/90 transition-colors disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
