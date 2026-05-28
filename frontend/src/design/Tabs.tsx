import type { ReactNode } from 'react';
import * as RadixTabs from '@radix-ui/react-tabs';

export type TabItem = {
  value: string;
  label: string;
  content: ReactNode;
};

type TabsProps = {
  value?: string;
  defaultValue?: string;
  items: TabItem[];
  onValueChange?: (value: string) => void;
};

export function Tabs({ value, defaultValue, items, onValueChange }: TabsProps) {
  const resolvedDefault = defaultValue || items[0]?.value;
  return (
    <RadixTabs.Root className="tabs-root" value={value} defaultValue={resolvedDefault} onValueChange={onValueChange}>
      <RadixTabs.List className="tabs-list">
        {items.map((item) => (
          <RadixTabs.Trigger className="tabs-trigger" key={item.value} value={item.value}>
            {item.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((item) => (
        <RadixTabs.Content key={item.value} value={item.value}>
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
