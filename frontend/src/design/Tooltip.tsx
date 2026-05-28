import type { ReactNode } from 'react';
import * as RadixTooltip from '@radix-ui/react-tooltip';

type TooltipProps = {
  label: ReactNode;
  children: ReactNode;
};

export function Tooltip({ label, children }: TooltipProps) {
  return (
    <RadixTooltip.Provider delayDuration={180}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content className="tooltip-content" sideOffset={6}>
            {label}
            <RadixTooltip.Arrow />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
