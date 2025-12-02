import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ThemeContext } from './ThemeContext';

const resolveInitialTheme = () => {
    if (typeof window === 'undefined') {
        return 'light';
    }
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    return media && media.matches ? 'dark' : 'light';
};

const ThemeProvider = ({ children }) => {
    const [theme, setTheme] = useState(resolveInitialTheme);

    useEffect(() => {
        if (typeof document === 'undefined') {
            return;
        }
        const root = document.documentElement;
        root.dataset.theme = theme;
        root.style.colorScheme = theme;
    }, [theme]);

    const toggleTheme = useCallback(() => {
        setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
    }, []);

    const contextValue = useMemo(() => ({
        theme,
        setTheme,
        toggleTheme
    }), [theme, toggleTheme]);

    return (
        <ThemeContext.Provider value={contextValue}>
            {children}
        </ThemeContext.Provider>
    );
};

export default ThemeProvider;
