import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Button } from './Button';
import { Select, type SelectOption } from './Select';

type EditDialogProps = {
  open: boolean;
  title: string;
  label: string;
  value: string;
  mode?: 'text' | 'textarea' | 'select';
  options?: SelectOption[];
  busy?: boolean;
  onSubmit: (value: string) => void;
  onOpenChange: (open: boolean) => void;
};

export function EditDialog({
  open,
  title,
  label,
  value,
  mode = 'text',
  options = [],
  busy,
  onSubmit,
  onOpenChange,
}: EditDialogProps) {
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="drawer-overlay" />
        <Dialog.Content className="dialog-content">
          <Dialog.Title>{title}</Dialog.Title>
          <div className="form-field">
            <span>{label}</span>
            {mode === 'select' ? (
              <Select label={label} value={draft} onChange={setDraft} options={options} />
            ) : mode === 'textarea' ? (
              <textarea value={draft} rows={5} onChange={(event) => setDraft(event.target.value)} />
            ) : (
              <input value={draft} onChange={(event) => setDraft(event.target.value)} />
            )}
          </div>
          <div className="button-row dialog-actions">
            <Dialog.Close asChild>
              <Button disabled={busy} variant="secondary">
                取消
              </Button>
            </Dialog.Close>
            <Button disabled={busy} onClick={() => onSubmit(draft)} variant="primary">
              保存
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
