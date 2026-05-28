import { forwardRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  icon?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', icon, children, className, type = 'button', ...props },
  ref,
) {
  return (
    <button ref={ref} type={type} className={clsx('button', variant, className)} {...props}>
      {icon}
      {children}
    </button>
  );
});
