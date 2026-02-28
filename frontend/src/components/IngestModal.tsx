import { useState, useRef } from 'react';
import { X, Upload, Github, Youtube, Globe, Image as ImageIcon, Mic, Type, MessageSquare, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  uploadFiles, ingestGithub, ingestYoutube, ingestWebsite,
  ingestImage, ingestAudio, ingestAIChat, ingestText
} from '../services/api';

type Tool = 'file' | 'github' | 'youtube' | 'website' | 'image' | 'audio' | 'text' | 'aichat';

const TOOLS: { id: Tool; label: string; icon: any; color: string }[] = [
  { id: 'file',    label: 'File',      icon: Upload,       color: 'text-accent bg-accent/10' },
  { id: 'github',  label: 'GitHub',    icon: Github,       color: 'text-purple-500 bg-purple-500/10' },
  { id: 'youtube', label: 'YouTube',   icon: Youtube,      color: 'text-red-500 bg-red-500/10' },
  { id: 'website', label: 'Website',   icon: Globe,        color: 'text-cyan-500 bg-cyan-500/10' },
  { id: 'image',   label: 'Image',     icon: ImageIcon,    color: 'text-pink-500 bg-pink-500/10' },
  { id: 'audio',   label: 'Audio',     icon: Mic,          color: 'text-indigo-500 bg-indigo-500/10' },
  { id: 'text',    label: 'Text',      icon: Type,         color: 'text-green-500 bg-green-500/10' },
  { id: 'aichat',  label: 'AI Chat',   icon: MessageSquare,color: 'text-blue-500 bg-blue-500/10' },
];

interface Props {
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

export default function IngestModal({ onClose, onSuccess, onError }: Props) {
  const [active, setActive] = useState<Tool | null>(null);
  const [loading, setLoading] = useState(false);

  // inputs
  const [url, setUrl] = useState('');
  const [textName, setTextName] = useState('');
  const [textContent, setTextContent] = useState('');
  const [maxPages, setMaxPages] = useState(2);
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = () => { setUrl(''); setTextName(''); setTextContent(''); setFile(null); setMaxPages(2); };

  const selectTool = (id: Tool) => {
    setActive(id);
    reset();
    // file tool: open picker immediately
    if (id === 'file') setTimeout(() => fileInputRef.current?.click(), 50);
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (!files.length) return;
    setLoading(true);
    try {
      await uploadFiles(files);
      onSuccess(`${files.length} file(s) embedded`);
      onClose();
    } catch (e: any) {
      onError(e.response?.data?.detail || 'Upload failed');
    } finally { setLoading(false); }
  };

  const handleSubmit = async () => {
    setLoading(true);
    try {
      switch (active) {
        case 'github':  await ingestGithub(url); onSuccess('Repo ingestion started'); break;
        case 'youtube': await ingestYoutube(url); onSuccess('YouTube transcript embedded'); break;
        case 'website': await ingestWebsite(url, maxPages); onSuccess('Website embedded'); break;
        case 'image':   if (file) await ingestImage(file); onSuccess('Image embedded'); break;
        case 'audio':   if (file) await ingestAudio(file); onSuccess('Audio transcribed & embedded'); break;
        case 'text':    await ingestText(textContent, textName); onSuccess('Text embedded'); break;
        case 'aichat':  await ingestAIChat(url); onSuccess('AI Chat ingested'); break;
      }
      onClose();
    } catch (e: any) {
      onError(e.response?.data?.detail || 'Ingestion failed');
    } finally { setLoading(false); }
  };

  const canSubmit = () => {
    if (active === 'github' || active === 'youtube' || active === 'website' || active === 'aichat') return !!url;
    if (active === 'image' || active === 'audio') return !!file;
    if (active === 'text') return !!textContent && !!textName;
    return false;
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          className="bg-surface border border-border rounded-3xl w-full max-w-md shadow-2xl overflow-hidden"
          initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 40, opacity: 0 }}
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-border">
            <h2 className="font-bold text-sm uppercase tracking-widest">Embed Content</h2>
            <button onClick={onClose} className="p-1 rounded-lg hover:bg-surface2 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Tool Grid */}
          <div className="grid grid-cols-4 gap-2 p-4">
            {TOOLS.map(t => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  onClick={() => selectTool(t.id)}
                  className={`flex flex-col items-center gap-1.5 p-3 rounded-2xl transition-all border ${
                    active === t.id ? 'border-accent bg-accent/5' : 'border-transparent hover:bg-surface2'
                  }`}
                >
                  <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${t.color}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-bold">{t.label}</span>
                </button>
              );
            })}
          </div>

          {/* Hidden file input for "file" tool */}
          <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileChange} />

          {/* Tool-specific input */}
          <AnimatePresence>
            {active && active !== 'file' && (
              <motion.div
                initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4 flex flex-col gap-3">
                  <div className="h-px bg-border" />

                  {/* URL-based tools */}
                  {(active === 'github' || active === 'youtube' || active === 'website' || active === 'aichat') && (
                    <input
                      autoFocus
                      type="text"
                      placeholder={
                        active === 'github' ? 'https://github.com/user/repo' :
                        active === 'youtube' ? 'https://youtube.com/watch?v=...' :
                        active === 'aichat' ? 'ChatGPT / Claude share URL' :
                        'https://example.com'
                      }
                      value={url}
                      onChange={e => setUrl(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && canSubmit() && handleSubmit()}
                      className="w-full bg-surface2/50 border border-border rounded-xl py-2.5 px-3 text-sm focus:ring-1 focus:ring-accent outline-none"
                    />
                  )}

                  {/* Website max pages */}
                  {active === 'website' && (
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-text-muted font-bold">Max Pages:</label>
                      <input type="number" min="1" max="50" value={maxPages} onChange={e => setMaxPages(+e.target.value || 1)}
                        className="w-16 bg-surface2/50 border border-border rounded-lg py-1 px-2 text-xs outline-none focus:ring-1 focus:ring-accent" />
                    </div>
                  )}

                  {/* File-based tools (image/audio) */}
                  {(active === 'image' || active === 'audio') && (
                    <label className="flex flex-col items-center justify-center border-2 border-dashed border-border rounded-2xl py-6 cursor-pointer hover:border-accent/50 transition-colors">
                      <input
                        type="file"
                        accept={active === 'image' ? '.jpg,.jpeg,.png,.webp,.gif' : '.mp3,.wav,.m4a,.ogg,.flac'}
                        className="hidden"
                        onChange={e => setFile(e.target.files?.[0] || null)}
                      />
                      {file ? (
                        <p className="text-sm font-bold truncate max-w-[200px]">{file.name}</p>
                      ) : (
                        <>
                          {active === 'image' ? <ImageIcon className="w-6 h-6 text-text-muted mb-1" /> : <Mic className="w-6 h-6 text-text-muted mb-1" />}
                          <p className="text-xs text-text-muted">Click to select {active}</p>
                        </>
                      )}
                    </label>
                  )}

                  {/* Text tool */}
                  {active === 'text' && (
                    <>
                      <input autoFocus type="text" placeholder="Source name (e.g. meeting-notes)"
                        value={textName} onChange={e => setTextName(e.target.value)}
                        className="w-full bg-surface2/50 border border-border rounded-xl py-2.5 px-3 text-sm focus:ring-1 focus:ring-accent outline-none" />
                      <textarea rows={4} placeholder="Paste content here..."
                        value={textContent} onChange={e => setTextContent(e.target.value)}
                        className="w-full bg-surface2/50 border border-border rounded-xl py-2.5 px-3 text-sm focus:ring-1 focus:ring-accent outline-none resize-none" />
                    </>
                  )}

                  <button
                    onClick={handleSubmit}
                    disabled={loading || !canSubmit()}
                    className="w-full bg-accent text-white py-2.5 rounded-xl font-bold text-sm hover:bg-accent/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Embed'}
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
