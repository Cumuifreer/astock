import { QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from './AppShell';
import { queryClient } from './queryClient';
import '../design/tokens.css';

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  );
}
