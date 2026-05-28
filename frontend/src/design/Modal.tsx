import type { ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Button } from './Button';

type ModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
};

export function Modal({ open, onOpenChange, title, children }: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="drawer-overlay" />
        <Dialog.Content className="surface pad" style={{ position: 'fixed', zIndex: 42, inset: '12vh auto auto 50%', width: 'min(520px, 92vw)', transform: 'translateX(-50%)' }}>
          <Dialog.Title>{title}</Dialog.Title>
          <div style={{ marginTop: 16 }}>{children}</div>
          <div style={{ marginTop: 18 }}>
            <Dialog.Close asChild>
              <Button>关闭</Button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
