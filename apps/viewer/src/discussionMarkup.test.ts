import { describe, expect, it } from 'vitest';
import {
  MAX_DISCUSSION_MARKS,
  discussionMarksAfterCommand,
  discussionOrientationForImage,
  parseDiscussionMarks,
  roundedPatientPoint,
} from './discussionMarkup';
import type { DiscussionMark } from './discussionMarkup';

const mark = (id = 'mark_0123456789abcdef0123'): DiscussionMark => ({
  id,
  orientation: 'sagittal',
  color: 'cyan',
  author: 'person',
  points_lps_mm: [[1.25, -2.5, 3.75]],
});

describe('discussion markup', () => {
  it('accepts bounded patient-space marks without text or pixels', () => {
    expect(parseDiscussionMarks([mark()])).toEqual([mark()]);
    expect(roundedPatientPoint([1.2345, -2.3456, 3.4567])).toEqual([1.23, -2.35, 3.46]);
  });

  it('maps native DICOM planes to the shared discussion orientations', () => {
    expect(discussionOrientationForImage([1, 0, 0, 0, 1, 0])).toBe('axial');
    expect(discussionOrientationForImage([1, 0, 0, 0, 0, -1])).toBe('coronal');
    expect(discussionOrientationForImage([0, 1, 0, 0, 0, -1])).toBe('sagittal');
  });

  it('rejects unsupported colors, duplicate IDs, and oversized sets', () => {
    expect(parseDiscussionMarks([{ ...mark(), color: 'red' }])).toBeUndefined();
    expect(parseDiscussionMarks([mark(), mark()])).toBeUndefined();
    expect(
      parseDiscussionMarks(
        Array.from({ length: MAX_DISCUSSION_MARKS + 1 }, (_, index) =>
          mark(`mark_${index.toString(16).padStart(20, '0')}`),
        ),
      ),
    ).toBeUndefined();
  });

  it('preserves highlights when a navigation command omits overlay changes', () => {
    const current = [mark()];
    expect(discussionMarksAfterCommand(current)).toBe(current);
    expect(discussionMarksAfterCommand(current, [])).toEqual([]);
  });
});
