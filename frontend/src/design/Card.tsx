import type { HTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';

type CardProps = HTMLAttributes<HTMLElement> & {
  title?: ReactNode;
  description?: ReactNode;
};

export function Card({ title, description, children, className, ...props }: CardProps) {
  return (
    <section className={clsx('card', className)} {...props}>
      {title ? <h3 className="card-title">{title}</h3> : null}
      {description ? <p className="card-copy">{description}</p> : null}
      {children}
    </section>
  );
}
