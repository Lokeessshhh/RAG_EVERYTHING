import { Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { Toaster } from './components/Toast';

// Lazy load pages
const LandingPage = lazy(() => import('./pages/LandingPage'));
const AppShell = lazy(() => import('./components/AppShell'));
const UploadPage = lazy(() => import('./pages/UploadPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const LibraryPage = lazy(() => import('./pages/LibraryPage'));

function App() {
  return (
    <Toaster>
      <Suspense fallback={<div className="flex items-center justify-center h-screen bg-bg text-text">Loading...</div>}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/app" element={<AppShell />}>
            <Route index element={<Navigate to="/app/chat" replace />} />
            <Route path="upload" element={<UploadPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="library" element={<LibraryPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Toaster>
  );
}

export default App;
