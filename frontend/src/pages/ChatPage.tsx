import { useState, useRef, useEffect } from 'react';
import { 
  Mic, Send, Paperclip, Plus, Trash2, 
  ChevronRight, ChevronDown, ExternalLink, 
  MessageSquare, User, Bot, Loader2,
  Database
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { chatStream, getLibrary } from '../services/api';
import { useVoiceInput } from '../hooks/useVoiceInput';
import { useToast } from '../components/Toast';
import IngestModal from '../components/IngestModal';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: any[];
}

const ChatPage = () => {
  const { toast } = useToast();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [library, setLibrary] = useState<any>({});
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [isIngestOpen, setIsIngestOpen] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const inputRef = useRef(input);
  useEffect(() => {
    inputRef.current = input;
  }, [input]);

  const { isListening, toggleListening, error: voiceError } = useVoiceInput(
    (text) => setInput(text),
    () => {
      if (inputRef.current.trim()) {
        handleSend(inputRef.current);
      }
    }
  );

  useEffect(() => {
    if (voiceError) toast(voiceError, 'error');
  }, [voiceError]);

  useEffect(() => {
    fetchLibrary();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const fetchLibrary = async () => {
    try {
      const data = await getLibrary();
      setLibrary(data.sources);
    } catch (e) {
      console.error(e);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSend = async (textOverride?: string) => {
    const textToSend = textOverride || input;
    if (!textToSend.trim() || isLoading) return;

    const userMessage: Message = {
      id: Math.random().toString(36).substring(7),
      role: 'user',
      content: textToSend,
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    const assistantId = Math.random().toString(36).substring(7);
    const assistantMessage: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      sources: [],
    };

    setMessages(prev => [...prev, assistantMessage]);

    try {
      let fullContent = '';
      // Build last 6 messages (excluding the new user message and empty assistant placeholder)
      const history = messages
        .filter(m => m.content.trim() !== '')
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }));

      await chatStream(userMessage.content, selectedSources, (data) => {
        if (data.content) {
          fullContent += data.content;
          setMessages(prev => prev.map(m => 
            m.id === assistantId ? { ...m, content: fullContent } : m
          ));
        }
        if (data.sources) {
          setMessages(prev => prev.map(m => 
            m.id === assistantId ? { ...m, sources: data.sources } : m
          ));
        }
      }, history);
    } catch (e: any) {
      toast('Failed to get response', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleSource = (name: string) => {
    setSelectedSources(prev => 
      prev.includes(name) ? prev.filter(s => s !== name) : [...prev, name]
    );
  };

  const clearChat = () => {
    setMessages([]);
    toast('Chat cleared', 'info');
  };

  return (
    <>
    <div className="flex h-full overflow-hidden bg-bg">
      {/* Source Filter Sidebar */}
      <AnimatePresence initial={false}>
        {isSidebarOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="hidden lg:flex flex-col border-r border-border bg-surface shrink-0 overflow-hidden"
          >
            <div className="p-6 border-b border-border flex items-center justify-between">
              <h2 className="font-bold flex items-center gap-2 font-display uppercase tracking-wider text-xs text-text-muted">
                <Database className="w-4 h-4" /> Search in...
              </h2>
              <button 
                onClick={() => setSelectedSources([])}
                className="text-[10px] font-bold text-accent uppercase hover:underline"
              >
                Clear
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
              {Object.entries(library).map(([type, items]: [string, any]) => (
                <div key={type}>
                  <h3 className="text-[10px] font-bold text-text-muted uppercase tracking-widest mb-3 px-2 flex items-center justify-between">
                    {type}s
                    <span className="bg-surface2 px-1.5 py-0.5 rounded text-[8px]">{items.length}</span>
                  </h3>
                  <div className="space-y-1">
                    {items.map((item: any) => (
                      <label key={item.name} className="flex items-center gap-3 p-2 rounded-lg hover:bg-surface2 cursor-pointer transition-colors group">
                        <input 
                          type="checkbox" 
                          checked={selectedSources.includes(item.name)}
                          onChange={() => toggleSource(item.name)}
                          className="w-4 h-4 rounded border-border text-accent focus:ring-accent accent-accent"
                        />
                        <span className="text-sm truncate flex-1 group-hover:text-text transition-colors">
                          {item.name}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}

              {Object.keys(library).length === 0 && (
                <div className="text-center py-10 px-4 opacity-40">
                    <p className="text-xs">No sources found. Upload files to start chatting.</p>
                </div>
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Top Bar */}
        <header className="h-16 border-b border-border flex items-center justify-between px-6 shrink-0 bg-surface/80 backdrop-blur-md sticky top-0 z-20">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 rounded-lg hover:bg-surface2 transition-colors lg:flex hidden"
            >
              <Database className="w-5 h-5 text-text-muted" />
            </button>
            <h1 className="font-display font-bold text-lg">RAG Everything</h1>
          </div>
          
          <div className="flex items-center gap-3">
            <button 
              onClick={clearChat}
              className="p-2 rounded-lg hover:bg-red-500/10 text-text-muted hover:text-danger transition-all"
              title="Clear History"
            >
              <Trash2 className="w-5 h-5" />
            </button>
            <button 
              onClick={() => setMessages([])}
              className="bg-accent text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2 hover:scale-105 transition-transform"
            >
              <Plus className="w-4 h-4" /> New Chat
            </button>
          </div>
        </header>

        {/* Messages Container */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-8">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
              <div className="w-20 h-20 rounded-3xl bg-accent/10 flex items-center justify-center mb-6">
                <MessageSquare className="w-10 h-10 text-accent" />
              </div>
              <h2 className="text-2xl font-display mb-3">Ask anything about your data</h2>
              <p className="text-text-muted text-sm mb-8 leading-relaxed">
                Connect your documents and get instant answers with verifiable sources.
              </p>
              
              <div className="grid gap-3 w-full">
                {[
                  "Summarize my PDFs",
                  "Find functions in my code",
                  "What did I discuss in my chats?"
                ].map(suggestion => (
                  <button 
                    key={suggestion}
                    onClick={() => handleSend(suggestion)}
                    className="p-4 rounded-2xl border border-border bg-surface hover:border-accent hover:bg-accent/5 transition-all text-left text-sm font-medium group flex items-center justify-between"
                  >
                    {suggestion}
                    <ChevronRight className="w-4 h-4 opacity-0 group-hover:opacity-100 -translate-x-2 group-hover:translate-x-0 transition-all" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-8 w-full">
              {messages.map((message) => (
                <div 
                  key={message.id} 
                  className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <div className="flex items-center gap-2 mb-2 px-1">
                    {message.role === 'assistant' ? (
                      <>
                        <div className="w-6 h-6 rounded-lg bg-accent flex items-center justify-center">
                          <Bot className="w-4 h-4 text-white" />
                        </div>
                        <span className="text-xs font-bold uppercase tracking-widest text-text-muted">Assistant</span>
                      </>
                    ) : (
                      <>
                        <span className="text-xs font-bold uppercase tracking-widest text-text-muted">You</span>
                        <div className="w-6 h-6 rounded-lg bg-surface2 flex items-center justify-center">
                          <User className="w-4 h-4" />
                        </div>
                      </>
                    )}
                  </div>

                  <div className={`
                    p-4 md:p-6 rounded-3xl max-w-[90%] md:max-w-[80%] shadow-sm
                    ${message.role === 'user' 
                      ? 'bg-accent text-white rounded-tr-none' 
                      : 'bg-surface2 text-text rounded-tl-none border border-border/50'}
                  `}>
                    <div className="whitespace-pre-wrap leading-relaxed">
                      {message.content || (isLoading && <div className="flex gap-1.5 py-2">
                        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>)}
                    </div>
                  </div>

                  {message.role === 'assistant' && message.sources && message.sources.length > 0 && (
                    <SourceAccordion sources={message.sources} />
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-4 md:p-6 bg-gradient-to-t from-bg via-bg to-transparent relative z-10">
          <div className="max-w-3xl mx-auto relative">
            {/* Listening Indicator Overlay */}
            <AnimatePresence>
              {isListening && (
                <motion.div 
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="absolute -top-12 left-0 right-0 flex justify-center"
                >
                  <div className="bg-red-500 text-white px-4 py-1.5 rounded-full text-xs font-bold flex items-center gap-2 shadow-lg">
                    <div className="w-2 h-2 bg-white rounded-full animate-ping" />
                    Listening...
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="glass rounded-[28px] p-2 flex items-end gap-2 shadow-xl border-border/50 focus-within:border-accent/50 transition-all">
              <button onClick={() => setIsIngestOpen(true)} className="p-3 rounded-full hover:bg-surface2 text-text-muted transition-colors" title="Embed content">
                <Paperclip className="w-5 h-5" />
              </button>
              
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Ask a question about your documents..."
                className="flex-1 bg-transparent border-none outline-none py-3 px-2 resize-none min-h-[56px] max-h-40 font-body text-sm md:text-base"
                rows={1}
                style={{ height: 'auto' }}
              />

              <div className="flex items-center gap-1 p-1">
                <button 
                  onClick={toggleListening}
                  className={`
                    p-3 rounded-full transition-all relative
                    ${isListening ? 'bg-red-500 text-white shadow-lg shadow-red-500/20' : 'hover:bg-surface2 text-text-muted'}
                  `}
                >
                  <Mic className="w-5 h-5" />
                  {isListening && (
                    <motion.div 
                      layoutId="pulse"
                      className="absolute inset-0 rounded-full border-2 border-red-500"
                      initial={{ scale: 1, opacity: 1 }}
                      animate={{ scale: 1.5, opacity: 0 }}
                      transition={{ duration: 1.5, repeat: Infinity }}
                    />
                  )}
                </button>
                <button 
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isLoading}
                  className={`
                    p-3 rounded-full transition-all
                    ${input.trim() ? 'bg-accent text-white shadow-lg shadow-accent/20 hover:scale-105' : 'text-text-muted opacity-50'}
                  `}
                >
                  {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    {isIngestOpen && (
      <IngestModal
        onClose={() => setIsIngestOpen(false)}
        onSuccess={(msg) => { toast(msg, 'success'); fetchLibrary(); }}
        onError={(msg) => toast(msg, 'error')}
      />
    )}
    </>
  );
};

const SourceAccordion = ({ sources }: { sources: any[] }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mt-4 w-full max-w-[80%]">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-xs font-bold text-text-muted hover:text-accent transition-colors py-1 px-2 rounded-lg hover:bg-surface2"
      >
        {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        Sources Used ({sources.length})
      </button>
      
      <AnimatePresence>
        {isOpen && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="grid gap-2 mt-3 pl-2">
              {sources.map((source, i) => (
                <div key={i} className="p-3 rounded-xl bg-surface border border-border flex flex-col gap-2 hover:border-accent/30 transition-all">
                  <div className="flex items-center justify-between">
                    <span className="px-1.5 py-0.5 rounded bg-accent-light text-accent text-[9px] font-bold uppercase">
                      {source.source_type || 'DOC'}
                    </span>
                    <span className="text-[10px] text-text-muted truncate max-w-[150px]">
                      {source.source_name}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted line-clamp-2 leading-relaxed italic">
                    "{source.preview}"
                  </p>
                  <button className="text-[10px] font-bold text-accent flex items-center gap-1 hover:underline self-end">
                    View Chunk <ExternalLink className="w-2.5 h-2.5" />
                  </button>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ChatPage;
