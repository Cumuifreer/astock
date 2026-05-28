import type { ButtonHTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  icon?: ReactNode;
};

export function Button({ variant = 'secondary', icon, children, className, type = 'button', ...props }: ButtonProps) {
  return (
    <button type={type} className={clsx('button', variant, className)} {...props}>
      {icon}
      {children}
    </button>
  );
}
