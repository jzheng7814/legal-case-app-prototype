import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from './ThemeContext';

const ThemeToggle = () => {
    const { theme, toggleTheme } = useTheme();
    const isDark = theme === 'dark';
    const Icon = isDark ? Sun : Moon;
    const label = isDark ? 'Light mode' : 'Dark mode';

    return (
        <button
            type="button"
            onClick={toggleTheme}
            className="flex items-center gap-2 rounded-full border border-[var(--color-border-strong)] bg-[var(--color-surface-muted)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-primary)] transition hover:bg-[var(--color-surface-muted-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
        >
            <Icon className="h-4 w-4 text-[var(--color-text-primary)]" aria-hidden="true" />
            <span>{label}</span>
        </button>
    );
};

export default ThemeToggle;
