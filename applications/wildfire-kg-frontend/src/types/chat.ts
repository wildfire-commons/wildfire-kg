export interface Message {
  id: string;
  text: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
}

export interface ChatContext {
  recent_metrics?: string;
  data_sources?: string;
} 