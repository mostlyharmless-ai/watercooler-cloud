import React from 'react';
import { cn } from '@/lib/utils';

interface BaseButtonProps {
  variant?: 'primary' | 'ghost' | 'link';
}

interface ButtonAsButton extends BaseButtonProps, React.ButtonHTMLAttributes<HTMLButtonElement> {
  href?: never;
}

interface ButtonAsLink extends BaseButtonProps, React.AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string;
}

type ButtonProps = ButtonAsButton | ButtonAsLink;

export const Button = React.forwardRef<HTMLButtonElement | HTMLAnchorElement, ButtonProps>(
  ({ variant = 'primary', className, children, ...props }, ref) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-focus-ring focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:pointer-events-none';

    const variantStyles = {
      primary:
        'bg-accent text-background hover:bg-accent/90 px-6 py-3 rounded-lg font-semibold shadow-accent-glow hover:shadow-lg',
      ghost:
        'bg-transparent text-text-primary hover:bg-surface px-6 py-3 rounded-lg border border-border hover:border-accent/50',
      link: 'text-text-secondary hover:text-accent underline-offset-4 hover:underline',
    };

    if ('href' in props && props.href) {
      return (
        <a
          ref={ref as React.Ref<HTMLAnchorElement>}
          className={cn(baseStyles, variantStyles[variant], className)}
          {...(props as React.AnchorHTMLAttributes<HTMLAnchorElement>)}
        >
          {children}
        </a>
      );
    }

    return (
      <button
        ref={ref as React.Ref<HTMLButtonElement>}
        className={cn(baseStyles, variantStyles[variant], className)}
        {...(props as React.ButtonHTMLAttributes<HTMLButtonElement>)}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
