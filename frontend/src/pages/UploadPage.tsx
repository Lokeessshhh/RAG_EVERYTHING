import React, { useState, useCallback, useEffect } from 'react';
import { 
  Upload, Github, FileText, Code, Database, Loader2,
  Type, Youtube, Globe, Image as ImageIcon, Mic, X, MessageSquare
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  uploadFiles, ingestGithub, getLibrary,
  ingestText, ingestYoutube, ingestWebsite, ingestImage, ingestAudio, ingestAIChat
} from '../services/api';
import { useToast } from '../components/Toast';

const UploadPage = () => {
  const { toast } = useToast();
  
  // Existing states
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [githubUrl, setGithubUrl] = useState('');
  const [isGithubLoading, setIsGithubLoading] = useState(false);
  const [recentIngestions, setRecentIngestions] = useState<any[]>([]);

  // New states
  const [textContent, setTextContent] = useState('');
  const [textSourceName, setTextSourceName] = useState('');
  const [isTextLoading, setIsTextLoading] = useState(false);

  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [isYoutubeLoading, setIsYoutubeLoading] = useState(false);

  const [websiteUrl, setWebsiteUrl] = useState('');
  const [maxPages, setMaxPages] = useState(2);
  const [isWebsiteLoading, setIsWebsiteLoading] = useState(false);

  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [isImageLoading, setIsImageLoading] = useState(false);

  const [selectedAudio, setSelectedAudio] = useState<File | null>(null);
  const [audioDuration, setAudioDuration] = useState<string | null>(null);
  const [isAudioLoading, setIsAudioLoading] = useState(false);

  const [aiChatUrl, setAiChatUrl] = useState('');
  const [isAiChatLoading, setIsAiChatLoading] = useState(false);

  const fetchRecent = useCallback(async () => {
    try {
      const data = await getLibrary();
      const allSources: any[] = [];
      Object.entries(data.sources).forEach(([type, items]: [string, any]) => {
        items.forEach((item: any) => {
          allSources.push({ ...item, sourceType: type });
        });
      });
      
      setRecentIngestions(allSources.sort((a, b) => {
        if (a.ingested_at === 'unknown') return 1;
        if (b.ingested_at === 'unknown') return -1;
        return new Date(b.ingested_at).getTime() - new Date(a.ingested_at).getTime();
      }).slice(0, 5));
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    fetchRecent();
  }, [fetchRecent]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      await processFiles(files);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      await processFiles(files);
    }
  };

  const processFiles = async (files: File[]) => {
    setIsUploading(true);
    setUploadProgress(0);
    try {
      await uploadFiles(files, (p) => setUploadProgress(p));
      toast(`${files.length} files uploaded successfully`, 'success');
      fetchRecent();
    } catch (e: any) {
      toast(e.response?.data?.detail || 'Upload failed', 'error');
    } finally {
      setIsUploading(false);
    }
  };

  const handleGithubIngest = async () => {
    if (!githubUrl) return;
    setIsGithubLoading(true);
    try {
      await ingestGithub(githubUrl);
      toast('Repository ingestion started', 'success');
      setGithubUrl('');
      setTimeout(fetchRecent, 2000); // Wait for backend processing
    } catch (e: any) {
      toast(e.response?.data?.detail || 'GitHub ingestion failed', 'error');
    } finally {
      setIsGithubLoading(false);
    }
  };

  const handleTextIngest = async () => {
    if (!textContent || !textSourceName) return;
    setIsTextLoading(true);
    try {
      await ingestText(textContent, textSourceName);
      toast('Text embedded successfully', 'success');
      setTextContent('');
      setTextSourceName('');
      fetchRecent();
    } catch (e: any) {
      toast(e.response?.data?.detail || 'Text ingestion failed', 'error');
    } finally {
      setIsTextLoading(false);
    }
  };

  const handleYoutubeIngest = async () => {
    if (!youtubeUrl) return;
    setIsYoutubeLoading(true);
    try {
      await ingestYoutube(youtubeUrl);
      toast('YouTube transcript embedded successfully', 'success');
      setYoutubeUrl('');
      fetchRecent();
    } catch (e: any) {
      toast(e.response?.data?.detail || 'YouTube ingestion failed', 'error');
    } finally {
      setIsYoutubeLoading(false);
    }
  };

  const handleWebsiteIngest = async () => {
    if (!websiteUrl) return;
    setIsWebsiteLoading(true);
    try {
      await ingestWebsite(websiteUrl, maxPages);
      toast('Website content embedded successfully', 'success');
      setWebsiteUrl('');
      fetchRecent();
    } catch (e: any) {
      toast(e.response?.data?.detail || 'Website crawling failed', 'error');
    } finally {
      setIsWebsiteLoading(false);
    }
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedImage(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleImageDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) {
      setSelectedImage(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleImageIngest = async () => {
    if (!selectedImage) return;
    setIsImageLoading(true);
    try {
      await ingestImage(selectedImage);
      toast('Image content described and embedded', 'success');
      setSelectedImage(null);
      setImagePreview(null);
      fetchRecent();
    } catch (e: any) {
      toast(e.response?.data?.detail || 'Image ingestion failed', 'error');
    } finally {
      setIsImageLoading(false);
    }
  };

  const handleAudioChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processAudioFile(file);
    }
  };

  const handleAudioDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('audio/')) {
      processAudioFile(file);
    }
  };

  const processAudioFile = (file: File) => {
    setSelectedAudio(file);
    const audio = new Audio(URL.createObjectURL(file));
    audio.addEventListener('loadedmetadata', () => {
      const minutes = Math.floor(audio.duration / 60);
      const seconds = Math.floor(audio.duration % 60);
      setAudioDuration(`${minutes}:${seconds.toString().padStart(2, '0')}`);
    });
  };

  const handleAudioIngest = async () => {
    if (!selectedAudio) return;
    setIsAudioLoading(true);
    try {
      await ingestAudio(selectedAudio);
      toast('Audio transcribed and embedded', 'success');
      setSelectedAudio(null);
      setAudioDuration(null);
      fetchRecent();
    } catch (e: any) {
      toast(e.response?.data?.detail || 'Audio ingestion failed', 'error');
    } finally {
      setIsAudioLoading(false);
    }
  };

  const handleAiChatIngest = async () => {
    if (!aiChatUrl) return;
    setIsAiChatLoading(true);
    try {
      await ingestAIChat(aiChatUrl);
      toast('AI Chat ingested successfully', 'success');
      setAiChatUrl('');
      fetchRecent();
    } catch (e: any) {
      toast(e.response?.data?.detail || 'AI Chat ingestion failed', 'error');
    } finally {
      setIsAiChatLoading(false);
    }
  };

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto">
      <header className="mb-10">
        <h1 className="font-display text-3xl mb-2">Ingest Sources</h1>
        <p className="text-text-muted">Add documents to your knowledge base</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 1. File Upload */}
        <div className="bg-surface border border-border rounded-3xl p-6 flex flex-col gap-4 relative">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
              <Upload className="w-6 h-6 text-accent" />
            </div>
            <div>
              <h2 className="text-xl font-bold">File Upload</h2>
              <p className="text-text-muted text-sm">Upload PDF, TXT, CSV, or Code files</p>
            </div>
          </div>
          
          <div 
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`
              flex-1 relative border-2 border-dashed rounded-2xl transition-all duration-300 flex flex-col items-center justify-center p-4 min-h-[160px]
              ${isDragging ? 'border-accent bg-accent/5' : 'border-border bg-surface2/30 hover:border-accent/50'}
              ${isUploading ? 'pointer-events-none' : 'cursor-pointer'}
            `}
          >
            <input 
              type="file" 
              multiple 
              onChange={handleFileChange}
              className="absolute inset-0 opacity-0 cursor-pointer"
              disabled={isUploading}
            />
            {isUploading ? (
              <div className="w-full px-4 text-center">
                <div className="w-full h-1.5 bg-surface2 rounded-full overflow-hidden mb-2">
                  <motion.div 
                    className="h-full bg-accent"
                    initial={{ width: 0 }}
                    animate={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="text-xs font-medium">{uploadProgress}%</p>
              </div>
            ) : (
              <>
                <Upload className="w-8 h-8 text-text-muted mb-2" />
                <p className="text-sm font-bold text-center">Click or drag files</p>
              </>
            )}
          </div>
          <div className="flex flex-wrap gap-1 opacity-50">
            {['.pdf', '.txt', '.csv', '.py', '.js', '.ts'].map(ext => (
              <span key={ext} className="px-1.5 py-0.5 rounded bg-surface2 text-[8px] font-bold border border-border uppercase">{ext}</span>
            ))}
          </div>
        </div>

        {/* 2. GitHub */}
        <div className="bg-surface border border-border rounded-3xl p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center">
              <Github className="w-6 h-6 text-purple-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold">GitHub Repo</h2>
              <p className="text-text-muted text-sm">Ingest an entire public repository</p>
            </div>
          </div>
          <div className="flex-1 flex flex-col justify-center">
            <div className="relative">
              <Github className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input 
                type="text" 
                placeholder="https://github.com/username/repo"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                className="w-full bg-surface2/50 border border-border rounded-xl py-3 pl-10 pr-4 text-sm focus:ring-1 focus:ring-accent outline-none"
              />
            </div>
          </div>
          <button 
            onClick={handleGithubIngest}
            disabled={isGithubLoading || !githubUrl}
            className="w-full bg-text text-bg py-3 rounded-xl font-bold hover:bg-text/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isGithubLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Ingest Repo'}
          </button>
        </div>

        {/* 3. YouTube */}
        <div className="bg-surface border border-border rounded-3xl p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center">
              <Youtube className="w-6 h-6 text-red-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold">YouTube Video</h2>
              <p className="text-text-muted text-sm">Extract and embed video transcript</p>
            </div>
          </div>
          <div className="flex-1 flex flex-col justify-center">
            <div className="relative">
              <Youtube className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input 
                type="text" 
                placeholder="https://www.youtube.com/watch?v=..."
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                className="w-full bg-surface2/50 border border-border rounded-xl py-3 pl-10 pr-4 text-sm focus:ring-1 focus:ring-accent outline-none"
              />
            </div>
          </div>
          <button 
            onClick={handleYoutubeIngest}
            disabled={isYoutubeLoading || !youtubeUrl}
            className="w-full bg-text text-bg py-3 rounded-xl font-bold hover:bg-text/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isYoutubeLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Ingest Video'}
          </button>
        </div>

        {/* 4. Website */}
        <div className="bg-surface border border-border rounded-3xl p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 flex items-center justify-center">
              <Globe className="w-6 h-6 text-cyan-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold">Website</h2>
              <p className="text-text-muted text-sm">Crawl and embed content from a URL</p>
            </div>
          </div>
          <div className="flex-1 flex flex-col justify-center gap-3">
            <div className="relative">
              <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input 
                type="text" 
                placeholder="https://example.com/article"
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                className="w-full bg-surface2/50 border border-border rounded-xl py-3 pl-10 pr-4 text-sm focus:ring-1 focus:ring-accent outline-none"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-bold text-text-muted uppercase">Max Pages:</label>
              <input 
                type="number" 
                min="1"
                max="100"
                value={maxPages}
                onChange={(e) => setMaxPages(parseInt(e.target.value) || 1)}
                className="w-20 bg-surface2/50 border border-border rounded-lg py-1 px-2 text-xs focus:ring-1 focus:ring-accent outline-none"
              />
            </div>
          </div>
          <button 
            onClick={handleWebsiteIngest}
            disabled={isWebsiteLoading || !websiteUrl}
            className="w-full bg-text text-bg py-3 rounded-xl font-bold hover:bg-text/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isWebsiteLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Crawl & Ingest'}
          </button>
        </div>

        {/* 5. Image */}
        <div className="bg-surface border border-border rounded-3xl p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-pink-500/10 flex items-center justify-center">
              <ImageIcon className="w-6 h-6 text-pink-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold">Images</h2>
              <p className="text-text-muted text-sm">Visual analysis via Gemini Vision</p>
            </div>
          </div>
          <div 
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleImageDrop}
            className="flex-1 relative border-2 border-dashed border-border rounded-2xl bg-surface2/30 hover:border-accent/50 transition-all flex flex-col items-center justify-center min-h-[120px] overflow-hidden"
          >
            {imagePreview ? (
              <div className="relative w-full h-full group">
                <img src={imagePreview} alt="Preview" className="w-full h-full object-cover" />
                <button 
                  onClick={() => { setSelectedImage(null); setImagePreview(null); }}
                  className="absolute top-2 right-2 bg-bg/80 p-1 rounded-full hover:bg-bg transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center p-4">
                <input 
                  type="file" 
                  accept=".jpg,.jpeg,.png,.webp,.gif"
                  onChange={handleImageChange}
                  className="absolute inset-0 opacity-0 cursor-pointer"
                />
                <ImageIcon className="w-6 h-6 text-text-muted mb-2" />
                <p className="text-xs font-bold text-center">Drop image or click</p>
              </div>
            )}
          </div>
          <button 
            onClick={handleImageIngest}
            disabled={isImageLoading || !selectedImage}
            className="w-full bg-text text-bg py-3 rounded-xl font-bold hover:bg-text/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isImageLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Embed Images'}
          </button>
        </div>

        {/* 6. Audio */}
        <div className="bg-surface border border-border rounded-3xl p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center">
              <Mic className="w-6 h-6 text-indigo-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold">Audio</h2>
              <p className="text-text-muted text-sm">Transcribed via Whisper/STT</p>
            </div>
          </div>
          <div 
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleAudioDrop}
            className="flex-1 relative border-2 border-dashed border-border rounded-2xl bg-surface2/30 hover:border-accent/50 transition-all flex flex-col items-center justify-center min-h-[120px]"
          >
            {selectedAudio ? (
              <div className="p-4 text-center">
                <p className="text-sm font-bold truncate max-w-[200px]">{selectedAudio.name}</p>
                {audioDuration && <p className="text-xs text-text-muted mt-1">{audioDuration}</p>}
                <button 
                  onClick={() => { setSelectedAudio(null); setAudioDuration(null); }}
                  className="mt-2 text-xs text-accent hover:underline"
                >
                  Remove
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center p-4">
                <input 
                  type="file" 
                  accept=".mp3,.wav,.m4a,.ogg,.flac"
                  onChange={handleAudioChange}
                  className="absolute inset-0 opacity-0 cursor-pointer"
                />
                <Mic className="w-6 h-6 text-text-muted mb-2" />
                <p className="text-xs font-bold text-center">Drop audio or click</p>
              </div>
            )}
          </div>
          <button 
            onClick={handleAudioIngest}
            disabled={isAudioLoading || !selectedAudio}
            className="w-full bg-text text-bg py-3 rounded-xl font-bold hover:bg-text/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isAudioLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Transcribe & Embed'}
          </button>
        </div>

        {/* 7. Paste Text */}
        <div className="bg-surface border border-border rounded-3xl p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-green-500/10 flex items-center justify-center">
              <Type className="w-6 h-6 text-green-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold">Paste Text</h2>
              <p className="text-text-muted text-sm">Paste any text content directly</p>
            </div>
          </div>
          <div className="flex flex-col gap-2 flex-1">
            <input 
              type="text" 
              placeholder="Source name (e.g. meeting-notes)"
              value={textSourceName}
              onChange={(e) => setTextSourceName(e.target.value)}
              className="w-full bg-surface2/50 border border-border rounded-xl py-2 px-3 text-sm focus:ring-1 focus:ring-accent outline-none"
            />
            <textarea 
              placeholder="Paste your content here..."
              rows={4}
              value={textContent}
              onChange={(e) => setTextContent(e.target.value)}
              className="w-full bg-surface2/50 border border-border rounded-xl py-2 px-3 text-sm focus:ring-1 focus:ring-accent outline-none resize-none flex-1"
            />
          </div>
          <button 
            onClick={handleTextIngest}
            disabled={isTextLoading || !textContent || !textSourceName}
            className="w-full bg-text text-bg py-3 rounded-xl font-bold hover:bg-text/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isTextLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Embed Text'}
          </button>
        </div>

        {/* 8. AI Chat */}
        <div className="bg-surface border border-border rounded-3xl p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
              <MessageSquare className="w-6 h-6 text-blue-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold">AI Chat</h2>
              <p className="text-text-muted text-sm">Ingest AI chat conversations</p>
            </div>
          </div>
          <div className="flex-1 flex flex-col justify-center">
            <div className="relative">
              <MessageSquare className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input 
                type="text" 
                placeholder="Paste AI chat URL (e.g. ChatGPT share link)"
                value={aiChatUrl}
                onChange={(e) => setAiChatUrl(e.target.value)}
                className="w-full bg-surface2/50 border border-border rounded-xl py-3 pl-10 pr-4 text-sm focus:ring-1 focus:ring-accent outline-none"
              />
            </div>
          </div>
          <button 
            onClick={handleAiChatIngest}
            disabled={isAiChatLoading || !aiChatUrl}
            className="w-full bg-text text-bg py-3 rounded-xl font-bold hover:bg-text/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isAiChatLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Ingest Chat'}
          </button>
        </div>
      </div>

      {/* Recent Ingestions */}
      <section className="mt-20 mb-20">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold">Recently Added</h2>
          <button onClick={fetchRecent} className="text-accent text-sm font-bold hover:underline">Refresh</button>
        </div>
        <div className="flex flex-col gap-3">
          {recentIngestions.length === 0 ? (
            <div className="py-12 border border-dashed border-border rounded-3xl flex flex-col items-center gap-2 opacity-50">
              <Database className="w-8 h-8" />
              <p className="text-sm">No recent ingestions found</p>
            </div>
          ) : (
            recentIngestions.map((item, idx) => (
              <motion.div 
                key={idx}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.1 }}
                className="flex items-center gap-4 p-4 rounded-2xl bg-surface border border-border hover:border-accent/30 transition-all group"
              >
                <div className={`
                  w-10 h-10 rounded-xl flex items-center justify-center shrink-0
                  ${item.sourceType === 'pdf' ? 'bg-red-500/10 text-red-500' : 
                    item.sourceType === 'code' ? 'bg-amber-500/10 text-amber-500' : 
                    item.sourceType === 'github' ? 'bg-purple-500/10 text-purple-500' : 
                    item.sourceType === 'youtube' ? 'bg-red-500/10 text-red-500' :
                    item.sourceType === 'website' ? 'bg-cyan-500/10 text-cyan-500' :
                    item.sourceType === 'image' ? 'bg-pink-500/10 text-pink-500' :
                    item.sourceType === 'audio' || item.sourceType === 'voice' ? 'bg-indigo-500/10 text-indigo-500' :
                    item.sourceType === 'text' ? 'bg-green-500/10 text-green-500' : 'bg-accent/10 text-accent'}
                `}>
                  {item.sourceType === 'pdf' ? <FileText className="w-5 h-5" /> : 
                   item.sourceType === 'code' ? <Code className="w-5 h-5" /> : 
                   item.sourceType === 'github' ? <Github className="w-5 h-5" /> : 
                   item.sourceType === 'youtube' ? <Youtube className="w-5 h-5" /> :
                   item.sourceType === 'website' ? <Globe className="w-5 h-5" /> :
                   item.sourceType === 'image' ? <ImageIcon className="w-5 h-5" /> :
                   item.sourceType === 'audio' || item.sourceType === 'voice' ? <Mic className="w-5 h-5" /> :
                   item.sourceType === 'text' ? <Type className="w-5 h-5" /> : <Database className="w-5 h-5" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-bold truncate">{item.name}</p>
                  <p className="text-xs text-text-muted">
                    {item.chunks} chunks • {item.ingested_at !== 'unknown' ? new Date(item.ingested_at).toLocaleDateString() : 'Just now'}
                  </p>
                </div>
                <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-accent/5 text-accent text-[10px] font-bold uppercase">
                  {item.sourceType}
                </div>
              </motion.div>
            ))
          )}
        </div>
      </section>
    </div>
  );
};

export default UploadPage;
