import type { HTMLAttributes } from 'react';
import clsx from 'clsx';

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'good' | 'watch' | 'risk' | 'info' | 'purple';
};

export function Badge({ tone = 'neutral', className, ...props }: BadgeProps) {
  return <span className={clsx('badge', tone, className)} {...props} />;
}
