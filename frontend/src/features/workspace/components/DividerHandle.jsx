import React from 'react';

const DividerHandle = ({ onMouseDown }) => (
    <div
        role="separator"
        aria-orientation="vertical"
        tabIndex={-1}
        onMouseDown={(event) => {
            event.preventDefault();
            onMouseDown?.(event);
        }}
        className="w-2 shrink-0 cursor-col-resize bg-[var(--color-border)] hover:bg-[var(--color-border-strong)] active:bg-[var(--color-accent-soft)] transition-colors"
    >
        <div className="h-full w-px mx-auto bg-[var(--color-border-strong)]" />
    </div>
);

export default DividerHandle;
