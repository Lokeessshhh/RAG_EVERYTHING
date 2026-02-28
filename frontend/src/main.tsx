import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { BackendStatusProvider } from './context/BackendStatusContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BackendStatusProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </BackendStatusProvider>
  </StrictMode>,
)
