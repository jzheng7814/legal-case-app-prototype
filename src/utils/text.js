export const calculateTextChange = (previousText, nextText) => {
    if (previousText === nextText) {
        return null;
    }

    let start = 0;
    const prevLength = previousText.length;
    const nextLength = nextText.length;

    while (
        start < prevLength &&
        start < nextLength &&
        previousText[start] === nextText[start]
    ) {
        start += 1;
    }

    let prevEnd = prevLength - 1;
    let nextEnd = nextLength - 1;

    while (
        prevEnd >= start &&
        nextEnd >= start &&
        previousText[prevEnd] === nextText[nextEnd]
    ) {
        prevEnd -= 1;
        nextEnd -= 1;
    }

    const removedLength = prevEnd >= start ? prevEnd - start + 1 : 0;
    const insertedLength = nextEnd >= start ? nextEnd - start + 1 : 0;

    return {
        start,
        removedLength,
        insertedLength
    };
};

export const adjustRangeForChange = (range, change, maxLength) => {
    if (!range || !change) {
        return range;
    }

    const delta = change.insertedLength - change.removedLength;
    const changeEnd = change.start + change.removedLength;

    let { start, end } = range;

    if (changeEnd <= start) {
        start += delta;
        end += delta;
    } else if (change.start >= end) {
        // Change is after range; nothing to do
    } else {
        if (change.start < start) {
            start = change.start;
        }
        end += delta;
    }

    start = Math.max(0, start);
    end = Math.max(start, end);
    const clampedEnd = Math.min(end, maxLength);
    const clampedStart = Math.min(start, clampedEnd);

    return {
        start: clampedStart,
        end: clampedEnd
    };
};

export const buildChatTitle = (text) => {
    if (!text) {
        return 'Untitled Chat';
    }
    return text.length > 30 ? `${text.slice(0, 30)}...` : text;
};
