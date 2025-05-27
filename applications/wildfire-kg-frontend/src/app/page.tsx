'use client';

import { useState, useEffect } from 'react';
import { generateId } from '@/utils/id';
import { Message } from '@/types/chat';

interface ChatContext {
  kg_results?: any;
  rag_results?: any;
  weather_results?: any;
}

const GRAPH_NAME = 'wildfire-kg';

interface StreamData {
  type?: string;
  values?: {
    messages?: string;
    response?: string;
    kg_results?: any;
    rag_results?: any;
    weather_results?: any;
    error?: string;
    metadata?: any;
  };
  error?: {
    error: string;
    message: string;
  };
}

interface ThinkingStep {
  id: string;
  type: string;
  content: any;
  timestamp: Date;
}

interface ExtendedMessage extends Message {
  thinkingSteps?: ThinkingStep[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ExtendedMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [context, setContext] = useState<ChatContext | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  const createThread = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/threads`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });

      if (!response.ok) {
        throw new Error('Failed to create thread');
      }

      const data = await response.json();
      setThreadId(data.thread_id);
      return data.thread_id;
    } catch (error) {
      console.error('Failed to create thread:', error);
      return null;
    }
  };

  // Create a new thread when the component mounts
  useEffect(() => {
    createThread();
  }, []);

  const toggleThinkingStep = (messageId: string) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
  };

  const handleStreamResponse = async (response: Response) => {
    const reader = response.body?.getReader();
    if (!reader) return;
    
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = new TextDecoder().decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (!line.trim()) continue;

          if (line.startsWith('event: ')) {
            const eventType = line.slice(7).trim();
            const dataLine = lines.find(l => l.startsWith('data:'));
            if (!dataLine) continue;

            try {
              const data = JSON.parse(dataLine.slice(5));

              if (eventType === 'values' && data.messages?.[0]?.content) {
                // Update the final response text
                setMessages(prev => {
                  const newMessages = [...prev];
                  const lastMessage = newMessages[newMessages.length - 1];
                  if (lastMessage && lastMessage.sender === 'assistant') {
                    lastMessage.text = data.messages[0].content;
                  }
                  return newMessages;
                });

                // Store results in context if available
                if (data.kg_results || data.rag_results || data.weather_results) {
                  setContext({
                    kg_results: data.kg_results,
                    rag_results: data.rag_results,
                    weather_results: data.weather_results
                  });
                }
              }
            } catch (e) {
              console.error('Error parsing stream data:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('Error reading stream:', error);
    } finally {
      reader.releaseLock();
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    // If no thread exists, create one before sending the message
    if (!threadId) {
      const newThreadId = await createThread();
      if (!newThreadId) {
        setMessages(prev => [...prev, {
          id: generateId(),
          text: 'Sorry, I encountered an error creating the conversation. Please try again.',
          sender: 'assistant',
          timestamp: new Date(),
        }]);
        return;
      }
    }

    const userMessage: ExtendedMessage = {
      id: generateId(),
      text: input,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    
    // Add a placeholder message for the assistant's response
    setMessages(prev => [...prev, {
      id: generateId(),
      text: '',
      sender: 'assistant',
      timestamp: new Date(),
    }]);
    
    setInput('');
    setLoading(true);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/threads/${threadId}/runs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          assistant_id: GRAPH_NAME,
          input: {
            user_query: input,
            history: messages.map(msg => ({
              id: msg.id,
              text: msg.text,
              sender: msg.sender,
              timestamp: msg.timestamp.toISOString()
            }))
          }
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();
      
      // Update the assistant's message with the response
      setMessages(prev => {
        const newMessages = [...prev];
        const lastMessage = newMessages[newMessages.length - 1];
        if (lastMessage && lastMessage.sender === 'assistant') {
          lastMessage.text = data.messages[0]?.content || 'Sorry, I encountered an error. Please try again.';
        }
        return newMessages;
      });

      // Update context if results are available
      if (data.kg_results || data.rag_results || data.weather_results) {
        setContext({
          kg_results: data.kg_results,
          rag_results: data.rag_results,
          weather_results: data.weather_results
        });
      }

    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => {
        const newMessages = [...prev];
        const lastMessage = newMessages[newMessages.length - 1];
        if (lastMessage && lastMessage.sender === 'assistant') {
          lastMessage.text = 'Sorry, I encountered an error. Please try again.';
        }
        return newMessages;
      });
    } finally {
      setLoading(false);
    }
  };

  const renderThinkingSteps = (steps: ThinkingStep[]) => {
    return steps.map(step => (
      <div key={step.id} className="ml-4 mt-2 text-sm">
        <div className="text-gray-500 italic">
          {step.type === 'thinking' && (
            <div>
              {step.content.text && <div>{step.content.text}</div>}
              {step.content.tool_calls && (
                <div className="mt-1">
                  <span className="font-medium">Tool Calls:</span>
                  <pre className="bg-gray-50 p-2 mt-1 rounded text-xs overflow-x-auto">
                    {JSON.stringify(step.content.tool_calls, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
          {step.type === 'results' && (
            <div>
              {step.content.kg_results && (
                <div className="mt-1">
                  <span className="font-medium">Knowledge Graph Results:</span>
                  <pre className="bg-gray-50 p-2 mt-1 rounded text-xs overflow-x-auto">
                    {JSON.stringify(step.content.kg_results, null, 2)}
                  </pre>
                </div>
              )}
              {step.content.rag_results && (
                <div className="mt-1">
                  <span className="font-medium">RAG Results:</span>
                  <pre className="bg-gray-50 p-2 mt-1 rounded text-xs overflow-x-auto">
                    {JSON.stringify(step.content.rag_results, null, 2)}
                  </pre>
                </div>
              )}
              {step.content.weather_results && (
                <div className="mt-1">
                  <span className="font-medium">Weather Results:</span>
                  <pre className="bg-gray-50 p-2 mt-1 rounded text-xs overflow-x-auto">
                    {JSON.stringify(step.content.weather_results, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    ));
  };

  return (
    <div className="max-w-4xl mx-auto p-4">
      <div className="flex flex-col h-[calc(100vh-8rem)]">
        <div className="flex-1 overflow-y-auto mb-4 space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${
                message.sender === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              <div
                className={`max-w-[80%] rounded-lg p-4 ${
                  message.sender === 'user'
                    ? 'bg-[#03619B] text-white'
                    : 'bg-gray-100'
                }`}
              >
                <p>{message.text}</p>
                <p className="text-xs mt-2 opacity-70">
                  {message.timestamp.toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))}
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
