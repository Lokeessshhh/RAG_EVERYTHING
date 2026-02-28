import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
});

export const getLibrary = async () => {
  const response = await api.get('/library');
  return response.data;
};

export const deleteSource = async (sourceName: string) => {
  const response = await api.delete(`/library?source_name=${encodeURIComponent(sourceName)}`);
  return response.data;
};

export const uploadFiles = async (files: File[], onProgress?: (progress: number) => void) => {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));
  const response = await api.post('/ingest/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        onProgress(Math.round((progressEvent.loaded * 100) / progressEvent.total));
      }
    }
  });
  return response.data;
};

export const ingestGithub = async (repoUrl: string) => {
  const response = await api.post('/ingest/github', { url: repoUrl });
  return response.data;
};

export const ingestText = async (content: string, sourceName: string) => {
  const response = await api.post('/ingest/text', { content, source_name: sourceName });
  return response.data;
};

export const ingestYoutube = async (url: string) => {
  const response = await api.post('/ingest/youtube', { url });
  return response.data;
};

export const ingestWebsite = async (url: string, maxPages: number = 2) => {
  const response = await api.post('/ingest/website', { url, max_pages: maxPages });
  return response.data;
};

export const ingestImage = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/ingest/image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const ingestAudio = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/ingest/audio', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const ingestAIChat = async (url: string) => {
  const response = await api.post('/ingest/ai-chat', { url });
  return response.data;
};

export const getStats = async () => {
  const response = await api.get('/stats');
  return response.data;
};

export const chatStream = async (
  query: string, 
  source_types: string[], 
  onChunk: (data: { content?: string; sources?: any[] }) => void,
  conversation_history?: { role: string; content: string }[]
) => {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, source_types, conversation_history }),
  });

  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmedLine = line.trim();
      if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;
      
      const data = trimmedLine.slice(6);
      if (data === '[DONE]') break;
      
      try {
        const parsed = JSON.parse(data);
        onChunk(parsed);
      } catch (e) {
        console.error('Error parsing SSE chunk', e);
      }
    }
  }
};

export default api;
