import { QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from './AppShell';
import { queryClient } from './queryClient';
import { ToastProvider } from '../design/Toast';
import '../design/tokens.css';

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AppShell />
      </ToastProvider>
    </QueryClientProvider>
  );
}
