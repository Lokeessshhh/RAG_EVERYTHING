import { NavLink, Outlet, Link, useLocation } from 'react-router-dom';
import { 
  Upload, MessageSquare, Database 
} from 'lucide-react';
import { motion } from 'framer-motion';
import { ThemeToggle } from './ThemeToggle';
import { useEffect } from 'react';
import { useBackendStatus } from '../context/BackendStatusContext';

const AppShell = () => {
  const location = useLocation();
  const { status, checkBackend } = useBackendStatus();

  useEffect(() => {
    checkBackend();
  }, [checkBackend]);

  const dotClassName = status === 'online'
    ? 'bg-emerald-500'
    : status === 'connecting'
      ? 'bg-red-500 animate-pulse'
      : 'bg-red-500';

  const navLinks = [
    { to: '/app/upload', label: 'Upload', icon: Upload },
    { to: '/app/chat', label: 'Chat', icon: MessageSquare },
    { to: '/app/library', label: 'Library', icon: Database },
  ];

  return (
    <div className="flex h-screen bg-bg text-text overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex flex-col w-60 border-r border-border bg-surface shrink-0">
        <div className="p-6">
          <Link to="/" className="flex items-center gap-2 mb-8">
            <div className={`w-2.5 h-2.5 rounded-full ${dotClassName}`} />
            <span className="font-display text-xl font-bold tracking-tight">RAG Everything</span>
          </Link>

          <nav className="flex flex-col gap-2">
            {navLinks.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) => `
                  flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-all group
                  ${isActive 
                    ? 'bg-accent text-white shadow-lg shadow-accent/20' 
                    : 'text-text-muted hover:bg-surface2 hover:text-text'}
                `}
              >
                <link.icon className="w-5 h-5 transition-transform group-hover:scale-110" />
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="mt-auto p-6 border-t border-border flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <ThemeToggle />
            <span className="text-[10px] font-bold text-text-muted">v1.0.0</span>
          </div>
        </div>
      </aside>

      {/* Mobile Rail (Tab Bar) */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 h-16 glass border-t border-border z-50 flex items-center justify-around px-4">
        {navLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => `
              flex flex-col items-center gap-1 transition-colors
              ${isActive ? 'text-accent' : 'text-text-muted'}
            `}
          >
            <link.icon className="w-6 h-6" />
            <span className="text-[10px] font-bold uppercase">{link.label}</span>
          </NavLink>
        ))}
        <div className="w-10 h-10 flex items-center justify-center">
            <ThemeToggle />
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        <header className="md:hidden h-14 border-b border-border flex items-center px-4 shrink-0 bg-surface/80 backdrop-blur-md">
           <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${dotClassName}`} />
            <span className="font-display font-bold">RAG Everything</span>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto pb-16 md:pb-0">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="h-full"
          >
            <Outlet />
          </motion.div>
        </div>
      </main>
    </div>
  );
};

export default AppShell;
