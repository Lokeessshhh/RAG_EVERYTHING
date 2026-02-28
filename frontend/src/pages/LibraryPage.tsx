import { useState, useEffect } from 'react';
import { 
  Search, Trash2, Database, Layers, 
  FileText, Code, Github, MessageSquare, 
  BarChart2, PieChart
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getLibrary, deleteSource, getStats } from '../services/api';
import { useToast } from '../components/Toast';

const LibraryPage = () => {
  const { toast } = useToast();
  const [library, setLibrary] = useState<any>({});
  const [stats, setStats] = useState<any>(null);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [libData, statsData] = await Promise.all([
        getLibrary(),
        getStats()
      ]);
      setLibrary(libData.sources);
      setStats(statsData);
    } catch (e) {
      toast('Failed to load library', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await deleteSource(name);
      toast('Source deleted', 'success');
      fetchData();
    } catch (e) {
      toast('Delete failed', 'error');
    } finally {
      setDeletingId(null);
    }
  };

  const allSources = Object.entries(library).flatMap(([type, items]: [string, any]) => 
    items.map((item: any) => ({ ...item, sourceType: type }))
  ).filter((s: any) => s.name.toLowerCase().includes(search.toLowerCase()));

  const statsCards = [
    { label: 'Total Sources', value: allSources.length, icon: Database },
    { label: 'Total Chunks', value: allSources.reduce((acc: number, s: any) => acc + s.chunks, 0), icon: Layers },
    { label: 'Source Types', value: Object.keys(library).length, icon: PieChart },
    { label: 'API Calls', value: stats?.daily_count || 0, icon: BarChart2 },
  ];

  const getTypeStyle = (type: string) => {
    switch(type.toLowerCase()) {
      case 'pdf': return 'bg-red-500/10 text-red-500 border-red-500/20';
      case 'csv': return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
      case 'code': return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
      case 'github': return 'bg-purple-500/10 text-purple-500 border-purple-500/20';
      case 'text': return 'bg-accent/10 text-accent border-accent/20';
      case 'chat': return 'bg-orange-500/10 text-orange-500 border-orange-500/20';
      default: return 'bg-surface2 text-text-muted border-border';
    }
  };

  const getTypeIcon = (type: string) => {
    switch(type.toLowerCase()) {
      case 'pdf': return FileText;
      case 'code': return Code;
      case 'github': return Github;
      case 'chat': return MessageSquare;
      default: return Database;
    }
  };

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto">
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
        <div>
          <h1 className="font-display text-3xl mb-2">Knowledge Library</h1>
          <p className="text-text-muted">Manage and explore your ingested data</p>
        </div>
        
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" />
          <input 
            type="text" 
            placeholder="Search sources..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full md:w-80 bg-surface border border-border rounded-2xl py-3 pl-12 pr-4 outline-none focus:border-accent transition-all"
          />
        </div>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
        {statsCards.map((stat, i) => (
          <motion.div 
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="p-6 rounded-3xl bg-surface border border-border flex flex-col gap-2 relative overflow-hidden group"
          >
            <stat.icon className="absolute -top-2 -right-2 w-16 h-16 text-accent opacity-[0.03] group-hover:scale-110 transition-transform" />
            <span className="text-4xl font-display font-bold">{stat.value}</span>
            <span className="text-xs font-bold text-text-muted uppercase tracking-widest">{stat.label}</span>
          </motion.div>
        ))}
      </div>

      {/* Table */}
      <div className="bg-surface border border-border rounded-3xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface2/50 text-[10px] font-bold uppercase tracking-widest text-text-muted">
                <th className="px-6 py-4">Type</th>
                <th className="px-6 py-4">Name</th>
                <th className="px-6 py-4">Chunks</th>
                <th className="px-6 py-4">Date Added</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-6 py-4"><div className="w-12 h-6 bg-surface2 rounded" /></td>
                    <td className="px-6 py-4"><div className="w-48 h-4 bg-surface2 rounded" /></td>
                    <td className="px-6 py-4"><div className="w-8 h-4 bg-surface2 rounded" /></td>
                    <td className="px-6 py-4"><div className="w-24 h-4 bg-surface2 rounded" /></td>
                    <td className="px-6 py-4"><div className="w-8 h-8 bg-surface2 rounded ml-auto" /></td>
                  </tr>
                ))
              ) : allSources.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-20 text-center text-text-muted">
                    <div className="flex flex-col items-center gap-4 opacity-50">
                      <Database className="w-12 h-12" />
                      <p>No sources found. Upload something to get started.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                allSources.map((source: any, i: number) => {
                  const Icon = getTypeIcon(source.sourceType);
                  return (
                    <motion.tr 
                      key={source.name}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.05 }}
                      className="group hover:bg-surface2/30 transition-colors"
                    >
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded-md text-[10px] font-bold border uppercase flex items-center gap-1.5 w-fit ${getTypeStyle(source.sourceType)}`}>
                          <Icon className="w-3 h-3" />
                          {source.sourceType}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="font-bold text-sm">{source.name}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-sm font-mono text-text-muted">{source.chunks}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-xs text-text-muted">
                          {source.ingested_at !== 'unknown' ? new Date(source.ingested_at).toLocaleDateString() : 'Unknown'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                           <AnimatePresence mode="wait">
                            {deletingId === source.name ? (
                              <motion.div 
                                key="confirm"
                                initial={{ opacity: 0, scale: 0.9 }}
                                animate={{ opacity: 1, scale: 1 }}
                                className="flex items-center gap-2"
                              >
                                <button 
                                  onClick={() => handleDelete(source.name)}
                                  className="text-[10px] font-bold text-danger hover:underline"
                                >
                                  Confirm
                                </button>
                                <button 
                                  onClick={() => setDeletingId(null)}
                                  className="text-[10px] font-bold text-text-muted hover:underline"
                                >
                                  Cancel
                                </button>
                              </motion.div>
                            ) : (
                              <button 
                                onClick={() => setDeletingId(source.name)}
                                className="p-2 rounded-lg hover:bg-red-500/10 text-text-muted hover:text-danger opacity-0 group-hover:opacity-100 transition-all"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                           </AnimatePresence>
                        </div>
                      </td>
                    </motion.tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default LibraryPage;
