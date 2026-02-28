import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { API_BASE_URL } from '../services/api';

type BackendStatus = 'connecting' | 'online' | 'offline';

type BackendStatusContextValue = {
  status: BackendStatus;
  checkBackend: () => Promise<boolean>;
};

const BackendStatusContext = createContext<BackendStatusContextValue | undefined>(undefined);

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export const BackendStatusProvider = ({ children }: { children: React.ReactNode }) => {
  const [status, setStatus] = useState<BackendStatus>('offline');
  const inFlightRef = useRef<Promise<boolean> | null>(null);

  const checkBackend = useCallback(async () => {
    if (inFlightRef.current) return inFlightRef.current;

    const run = (async () => {
      setStatus('connecting');

      const url = `${API_BASE_URL}/test`;
      const delays = [0, 1000, 2000, 3000, 5000];

      for (let i = 0; i < delays.length; i++) {
        if (delays[i] > 0) await sleep(delays[i]);

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);

        try {
          const resp = await fetch(url, {
            method: 'GET',
            signal: controller.signal,
            cache: 'no-store',
          });

          if (resp.ok) {
            setStatus('online');
            return true;
          }
        } catch {
        } finally {
          clearTimeout(timeout);
        }
      }

      setStatus('offline');
      return false;
    })();

    inFlightRef.current = run;

    try {
      return await run;
    } finally {
      inFlightRef.current = null;
    }
  }, []);

  const value = useMemo(() => ({ status, checkBackend }), [status, checkBackend]);

  return (
    <BackendStatusContext.Provider value={value}>
      {children}
    </BackendStatusContext.Provider>
  );
};

export const useBackendStatus = () => {
  const ctx = useContext(BackendStatusContext);
  if (!ctx) throw new Error('useBackendStatus must be used within BackendStatusProvider');
  return ctx;
};
