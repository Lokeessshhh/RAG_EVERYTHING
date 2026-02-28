import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { 
  ArrowRight, Github, Search, Link as LinkIcon, Mic, 
  Layers, Upload, Cpu, MessageSquare, ChevronDown 
} from 'lucide-react';
import { ThemeToggle } from '../components/ThemeToggle';
import { ThreeBackground } from '../components/ThreeBackground';
import { WireframeShape } from '../components/WireframeShape';
import ErrorBoundary from '../components/ErrorBoundary';
import { useBackendStatus } from '../context/BackendStatusContext';

const LandingPage = () => {
  const [scrolled, setScrolled] = useState(false);
  const { status, checkBackend } = useBackendStatus();

  const dotClassName = status === 'online'
    ? 'bg-emerald-500'
    : status === 'connecting'
      ? 'bg-red-500 animate-pulse'
      : 'bg-red-500';

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    checkBackend();
  }, [checkBackend]);

  return (
    <div className="min-h-screen bg-bg text-text selection:bg-accent selection:text-white overflow-x-hidden">
      {/* Navbar */}
      <nav className={`fixed top-0 left-0 right-0 h-16 z-50 transition-all duration-300 ${
        scrolled ? 'glass border-b border-border shadow-sm' : 'bg-transparent'
      }`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-full flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${dotClassName}`} />
            <span className="font-display text-xl font-bold tracking-tight">RAG Everything</span>
          </div>
          
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-text-muted">
            <a href="#features" className="hover:text-accent transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-accent transition-colors">How it works</a>
            <a href="#sources" className="hover:text-accent transition-colors">Sources</a>
          </div>

          <div className="flex items-center gap-4">
            <ThemeToggle />
            <Link to="/app" className="hidden sm:flex items-center gap-2 bg-accent text-white px-5 py-2 rounded-full font-medium hover:scale-105 transition-transform shadow-lg shadow-accent/20">
              Open App <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center pt-16 overflow-hidden">
        <ErrorBoundary fallback={<div className="absolute inset-0 bg-bg transition-colors duration-500 overflow-hidden" />}>
          <ThreeBackground />
        </ErrorBoundary>
        
        <div className="max-w-7xl mx-auto px-4 sm:px-6 grid md:grid-cols-[1.5fr_1fr] gap-10 md:gap-12 items-center w-full relative z-10">
          {/* Left Content */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
          >
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[10px] font-bold uppercase tracking-widest mb-6">
              Open Source • Free Tier • Production Ready
            </div>
            
            <h1 className="font-display text-4xl sm:text-6xl lg:text-8xl leading-[0.9] tracking-tighter mb-6">
              Chat with <br />
              <motion.span 
                className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-emerald-500 inline-block"
                animate={{ 
                  backgroundPosition: ['0% 50%', '100% 50%', '0% 50%'],
                }}
                transition={{ duration: 5, repeat: Infinity, ease: "linear" }}
                style={{ backgroundSize: '200% auto' }}
              >
                Everything
              </motion.span> <br />
              You Own.
            </h1>

            <p className="text-text-muted text-base sm:text-xl max-w-lg mb-10 font-body leading-relaxed">
              Ingest PDFs, code, CSVs, GitHub repos, chat exports and more. 
              Ask questions. Get answers with sources cited.
            </p>

            <div className="flex flex-wrap gap-4 mb-12">
              <Link to="/app" className="flex items-center gap-2 bg-accent text-white px-6 sm:px-8 py-4 rounded-xl font-bold text-base sm:text-lg hover:shadow-xl hover:shadow-accent/30 transition-all">
                Start for Free <ArrowRight className="w-5 h-5" />
              </Link>
              <a href="https://github.com/Lokeessshhh/RAG_EVERYTHING/" target="_blank" rel="noreferrer" className="flex items-center gap-2 bg-surface border border-border px-6 sm:px-8 py-4 rounded-xl font-bold text-base sm:text-lg hover:bg-surface2 transition-all">
                <Github className="w-5 h-5" /> View on GitHub
              </a>
            </div>

            <div className="flex items-center gap-6">
              <div className="flex flex-col">
                <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-2">Built on</span>
                <div className="flex items-center gap-4 opacity-70 grayscale hover:grayscale-0 transition-all">
                  <span className="flex items-center gap-1.5 font-bold text-sm">
                    <img src="https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d47353046551ce2b.svg" className="w-4 h-4" alt="Gemini" /> Gemini
                  </span>
                  <span className="flex items-center gap-1.5 font-bold text-sm">
                    <Cpu className="w-4 h-4" /> Llama 8B
                  </span>
                  <span className="flex items-center gap-1.5 font-bold text-sm">
                    <Layers className="w-4 h-4" /> Zilliz Cloud
                  </span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Right Content */}
          <div className="relative hidden md:block">
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 1, delay: 0.2 }}
            >
              <ErrorBoundary fallback={<div className="w-full h-[400px] flex items-center justify-center opacity-20"><div className="w-40 h-40 rounded-full border border-accent animate-pulse" /></div>}>
                <WireframeShape />
              </ErrorBoundary>
            </motion.div>

            {/* Floating Card */}
            <motion.div
              animate={{ y: [0, -20, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              className="absolute -bottom-10 -left-10 glass p-6 rounded-2xl shadow-2xl max-w-[280px] border-accent/20"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center">
                  <MessageSquare className="w-4 h-4 text-accent" />
                </div>
                <div className="h-2 w-24 bg-border rounded-full" />
              </div>
              <p className="text-xs text-text-muted leading-relaxed mb-4">
                "Based on your recent documents, the project architecture follows a hexagonal pattern..."
              </p>
              <div className="flex items-center gap-2">
                <div className="px-2 py-0.5 rounded bg-accent-light text-accent text-[8px] font-bold">SOURCE: arch.pdf</div>
              </div>
            </motion.div>
          </div>
        </div>

        <motion.div 
          animate={{ y: [0, 10, 0] }} 
          transition={{ duration: 2, repeat: Infinity }}
          className="absolute bottom-10 left-1/2 -translate-x-1/2 text-text-muted"
        >
          <ChevronDown className="w-6 h-6" />
        </motion.div>
      </section>

      {/* Marquee Section */}
      <section id="sources" className="py-24 bg-bg-secondary/50 overflow-hidden border-y border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 mb-16 text-center">
          <h2 className="font-display text-4xl mb-4">Every format. One conversation.</h2>
          <p className="text-text-muted">A unified knowledge base for all your distributed information.</p>
        </div>

        <div className="flex flex-col gap-8">
          {/* Row 1 */}
          <div className="flex gap-8 whitespace-nowrap overflow-hidden">
             <div className="flex gap-8 animate-marquee">
                {['Text', 'PDF', 'CSV', 'Code', 'GitHub Repo', 'Text', 'PDF', 'CSV', 'Code', 'GitHub Repo'].map((type, i) => (
                  <div key={i} className="w-40 h-40 glass rounded-3xl flex flex-col items-center justify-center gap-4 hover:-translate-y-2 transition-transform cursor-default group border-transparent hover:border-accent/30">
                    <div className="w-12 h-12 rounded-2xl bg-surface2 flex items-center justify-center group-hover:bg-accent/10 transition-colors">
                      {type === 'Text' && <Layers className="w-6 h-6 text-accent" />}
                      {type === 'PDF' && <LinkIcon className="w-6 h-6 text-accent" />}
                      {type === 'CSV' && <Search className="w-6 h-6 text-accent" />}
                      {type === 'Code' && <Cpu className="w-6 h-6 text-accent" />}
                      {type === 'GitHub Repo' && <Github className="w-6 h-6 text-accent" />}
                    </div>
                    <span className="font-bold text-sm">{type}</span>
                  </div>
                ))}
             </div>
          </div>

          {/* Row 2 */}
          <div className="flex gap-8 whitespace-nowrap overflow-hidden">
             <div className="flex gap-8 animate-marquee-reverse">
                {['Chat Exports', 'YouTube', 'Audio', 'Web', 'Images', 'Chat Exports', 'YouTube', 'Audio', 'Web', 'Images'].map((type, i) => (
                  <div key={i} className="w-40 h-40 glass rounded-3xl flex flex-col items-center justify-center gap-4 hover:-translate-y-2 transition-transform cursor-default group border-transparent hover:border-accent/30 opacity-60 hover:opacity-100">
                    <div className="w-12 h-12 rounded-2xl bg-surface2 flex items-center justify-center group-hover:bg-accent/10 transition-colors">
                      {type === 'Chat Exports' && <MessageSquare className="w-6 h-6 text-accent" />}
                      {type === 'YouTube' && <Upload className="w-6 h-6 text-accent" />}
                      {type === 'Audio' && <Mic className="w-6 h-6 text-accent" />}
                      {type === 'Web' && <Search className="w-6 h-6 text-accent" />}
                      {type === 'Images' && <Layers className="w-6 h-6 text-accent" />}
                    </div>
                    <span className="font-bold text-sm">{type}</span>
                  </div>
                ))}
             </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-32 bg-bg overflow-hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="grid md:grid-cols-3 gap-12 relative">
            {/* Connector Line */}
            <div className="absolute top-10 left-[15%] right-[15%] h-0.5 bg-border hidden md:block">
              <motion.div 
                initial={{ width: 0 }}
                whileInView={{ width: '100%' }}
                viewport={{ once: true }}
                transition={{ duration: 1.5 }}
                className="h-full bg-accent"
              />
            </div>

            {[
              { step: 1, title: 'Upload', desc: 'Drag and drop any supported file format.', icon: Upload },
              { step: 2, title: 'Index', desc: 'Vectors are generated and stored securely.', icon: Cpu },
              { step: 3, title: 'Chat', desc: 'Ask anything and get cited answers.', icon: MessageSquare },
            ].map((item, idx) => (
              <motion.div 
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.2 }}
                className="flex flex-col items-center text-center relative z-10"
              >
                <div className="w-20 h-20 rounded-full bg-surface border-4 border-bg flex items-center justify-center shadow-xl mb-6 group hover:border-accent transition-all">
                  <item.icon className="w-8 h-8 text-accent group-hover:scale-110 transition-transform" />
                </div>
                <div className="px-3 py-1 rounded-full bg-accent text-white text-[10px] font-bold mb-4">STEP {item.step}</div>
                <h3 className="text-2xl mb-2">{item.title}</h3>
                <p className="text-text-muted text-sm">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-32 bg-bg-secondary/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="grid md:grid-cols-2 gap-8">
            {[
              { title: 'Semantic Search', desc: 'Finds meaning, not just keywords. 768-dim vectors via Gemini.', icon: Search },
              { title: 'Source Citations', desc: 'Every answer shows exactly which document it came from.', icon: LinkIcon },
              { title: 'Voice Input', desc: 'Ask questions out loud. Web Speech API, no external service.', icon: Mic },
              { title: 'Multi-Format', desc: 'PDF, CSV, code, GitHub, chat exports - all in one index.', icon: Layers },
            ].map((f, i) => (
              <motion.div 
                key={i}
                whileHover={{ y: -5 }}
                className="p-8 rounded-3xl bg-surface border border-border flex gap-6 hover:border-accent/50 transition-all group"
              >
                <div className="w-16 h-16 shrink-0 rounded-2xl bg-accent/5 flex items-center justify-center relative">
                  <div className="absolute inset-0 bg-accent rounded-full scale-0 group-hover:scale-100 opacity-5 transition-transform" />
                  <f.icon className="w-8 h-8 text-accent" />
                </div>
                <div>
                  <h4 className="text-xl mb-2">{f.title}</h4>
                  <p className="text-text-muted leading-relaxed">{f.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-border mt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 grid md:grid-cols-3 gap-12 items-start">
          <div>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-2.5 h-2.5 rounded-full bg-accent" />
              <span className="font-display font-bold text-lg">RAG Everything</span>
            </div>
            <p className="text-sm text-text-muted leading-relaxed">
              The unified intelligence layer for your personal and professional documents.
            </p>
          </div>
          
          <div className="grid grid-cols-2 gap-8">
            <div className="flex flex-col gap-3">
              <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-1">Product</span>
              <a href="#" className="text-sm hover:text-accent">Features</a>
              <a href="#" className="text-sm hover:text-accent">Pricing</a>
              <a href="#" className="text-sm hover:text-accent">API Docs</a>
            </div>
            <div className="flex flex-col gap-3">
              <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-1">Legal</span>
              <a href="#" className="text-sm hover:text-accent">Privacy</a>
              <a href="#" className="text-sm hover:text-accent">Terms</a>
            </div>
          </div>

          <div className="flex flex-col items-end">
            <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-4">Powered by</span>
            <div className="flex items-center gap-4 grayscale opacity-50">
              <span className="text-xs font-bold">GEMINI</span>
              <span className="text-xs font-bold">MILVUS</span>
              <span className="text-xs font-bold">VITE</span>
            </div>
          </div>
        </div>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 mt-12 pt-8 border-t border-border flex justify-between items-center">
          <p className="text-[10px] text-text-muted"> 2026 RAG Everything. Built with for the open source community.</p>
          <div className="flex gap-4">
            <a href="#" className="text-text-muted hover:text-text transition-colors"><Github className="w-4 h-4" /></a>
          </div>
        </div>
      </footer>

      <style>{`
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes marquee-reverse {
          0% { transform: translateX(-50%); }
          100% { transform: translateX(0); }
        }
        .animate-marquee {
          animation: marquee 40s linear infinite;
        }
        .animate-marquee-reverse {
          animation: marquee-reverse 40s linear infinite;
        }
      `}</style>
    </div>
  );
};

export default LandingPage;
