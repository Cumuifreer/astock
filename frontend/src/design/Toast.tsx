import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { CheckCircle2, Info, XCircle } from 'lucide-react';

type ToastTone = 'success' | 'info' | 'danger';
type ToastItem = {
  id: number;
  tone: ToastTone;
  message: string;
};
type ToastContextValue = {
  showToast: (message: string, tone?: ToastTone) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const showToast = useCallback((message: string, tone: ToastTone = 'info') => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setItems((current) => [...current, { id, message, tone }].slice(-4));
    window.setTimeout(() => {
      setItems((current) => current.filter((item) => item.id !== id));
    }, 3600);
  }, []);
  const value = useMemo(() => ({ showToast }), [showToast]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="true">
        {items.map((item) => (
          <div className={`toast ${item.tone}`} key={item.id}>
            {item.tone === 'success' ? <CheckCircle2 size={16} /> : item.tone === 'danger' ? <XCircle size={16} /> : <Info size={16} />}
            <span>{item.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    return { showToast: () => undefined };
  }
  return context;
}
