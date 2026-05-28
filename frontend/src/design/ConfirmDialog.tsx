import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle } from 'lucide-react';
import { Button } from './Button';

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  cancelLabel = '取消',
  busy,
  onConfirm,
  onOpenChange,
}: ConfirmDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="drawer-overlay" />
        <Dialog.Content className="dialog-content">
          <div className="dialog-icon danger">
            <AlertTriangle size={20} />
          </div>
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description className="card-copy">{description}</Dialog.Description>
          <div className="button-row dialog-actions">
            <Dialog.Close asChild>
              <Button disabled={busy} variant="secondary">
                {cancelLabel}
              </Button>
            </Dialog.Close>
            <Button disabled={busy} onClick={onConfirm} variant="danger">
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
