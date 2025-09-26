export const supportsCssHighlight = () =>
    typeof window !== 'undefined' &&
    window.CSS &&
    window.CSS.highlights &&
    typeof window.Highlight === 'function';

export const computeOverlayRects = (container, range) => {
    const containerRect = container.getBoundingClientRect();
    return Array.from(range.getClientRects())
        .map((rect) => ({
            top: rect.top - containerRect.top + container.scrollTop,
            left: rect.left - containerRect.left + container.scrollLeft,
            width: rect.width,
            height: rect.height
        }))
        .filter((rect) => rect.width > 0 && rect.height > 0);
};

export const getOffsetsForRange = (container, range) => {
    if (!container || !range) {
        return null;
    }

    if (container instanceof HTMLTextAreaElement) {
        const { selectionStart, selectionEnd, value } = container;
        if (
            selectionStart == null ||
            selectionEnd == null ||
            selectionStart === selectionEnd
        ) {
            return null;
        }
        return {
            start: selectionStart,
            end: selectionEnd,
            text: value.slice(selectionStart, selectionEnd)
        };
    }

    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
        return null;
    }

    const preRange = range.cloneRange();
    preRange.selectNodeContents(container);
    preRange.setEnd(range.startContainer, range.startOffset);
    const start = preRange.toString().length;
    const selectedText = range.toString();
    const end = start + selectedText.length;
    preRange.detach?.();

    return { start, end, text: selectedText };
};

export const createRangeFromOffsets = (container, start, end) => {
    if (!container || start == null || end == null || start === end) {
        return null;
    }

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let currentPos = 0;
    let startNode = null;
    let endNode = null;
    let startOffset = 0;
    let endOffset = 0;

    while (walker.nextNode()) {
        const node = walker.currentNode;
        const nodeLength = node.textContent.length;

        if (!startNode && currentPos + nodeLength > start) {
            startNode = node;
            startOffset = start - currentPos;
        }

        if (!endNode && currentPos + nodeLength >= end) {
            endNode = node;
            endOffset = end - currentPos;
            break;
        }

        currentPos += nodeLength;
    }

    if (!startNode || !endNode) {
        return null;
    }

    const range = document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    return range;
};

export const scrollRangeIntoView = (container, range) => {
    if (!container || !range) {
        return;
    }

    const rects = range.getClientRects();
    if (!rects.length) {
        return;
    }

    const containerRect = container.getBoundingClientRect();
    const firstRect = rects[0];
    const lastRect = rects[rects.length - 1];
    const currentScrollTop = container.scrollTop || 0;
    const targetTop = firstRect.top - containerRect.top + currentScrollTop;
    const targetBottom = lastRect.bottom - containerRect.top + currentScrollTop;
    const targetMiddle = (targetTop + targetBottom) / 2;
    const desiredTop = Math.max(0, targetMiddle - container.clientHeight / 2);

    if (typeof container.scrollTo === 'function') {
        container.scrollTo({ top: desiredTop, behavior: 'smooth' });
    } else {
        container.scrollTop = desiredTop;
    }
};

export const scrollElementIntoContainer = (container, element) => {
    if (!container || !element) {
        return;
    }

    const containerRect = container.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const currentScrollTop = container.scrollTop || 0;
    const targetTop = elementRect.top - containerRect.top + currentScrollTop;
    const targetBottom = elementRect.bottom - containerRect.top + currentScrollTop;
    const targetMiddle = (targetTop + targetBottom) / 2;
    const desiredTop = Math.max(0, targetMiddle - container.clientHeight / 2);

    if (typeof container.scrollTo === 'function') {
        container.scrollTo({ top: desiredTop, behavior: 'smooth' });
    } else {
        container.scrollTop = desiredTop;
    }
};
