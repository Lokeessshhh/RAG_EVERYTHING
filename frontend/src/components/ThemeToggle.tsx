import { motion, AnimatePresence } from 'framer-motion';
import { Sun, Moon } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';

export const ThemeToggle = () => {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className="p-2 rounded-full hover:bg-surface2 transition-colors relative w-10 h-10 flex items-center justify-center overflow-hidden"
      aria-label="Toggle theme"
    >
      <AnimatePresence mode="wait">
        {theme === 'light' ? (
          <motion.div
            key="sun"
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -20, opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <Sun className="w-5 h-5 text-warning" />
          </motion.div>
        ) : (
          <motion.div
            key="moon"
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -20, opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <Moon className="w-5 h-5 text-accent" />
          </motion.div>
        )}
      </AnimatePresence>
    </button>
  );
};
