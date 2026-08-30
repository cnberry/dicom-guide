import type { MprOrientation } from './cornerstone';
import type { MprPatientPoint } from './mpr';

export const DISCUSSION_MARK_COLORS = {
  yellow: '#ffd166',
  cyan: '#67e8f9',
  violet: '#d8b4fe',
  green: '#6ee7b7',
} as const;

export type DiscussionMarkColor = keyof typeof DISCUSSION_MARK_COLORS;
export type DiscussionMark = {
  id: string;
  orientation: MprOrientation;
  color: DiscussionMarkColor;
  author: 'person' | 'agent';
  points_lps_mm: MprPatientPoint[];
};

export const MAX_DISCUSSION_MARKS = 256;
export const MAX_DISCUSSION_MARK_POINTS = 64;

const markIdPattern = /^mark_[0-9a-f]{20}$/;
const orientations = new Set<MprOrientation>(['axial', 'coronal', 'sagittal']);

const patientPoint = (value: unknown): MprPatientPoint | undefined => {
  if (
    !Array.isArray(value) ||
    value.length !== 3 ||
    !value.every(
      (coordinate) =>
        typeof coordinate === 'number' &&
        Number.isFinite(coordinate) &&
        Math.abs(coordinate) <= 1_000_000,
    )
  ) {
    return undefined;
  }
  return [value[0], value[1], value[2]];
};

export const parseDiscussionMarks = (value: unknown): DiscussionMark[] | undefined => {
  if (!Array.isArray(value) || value.length > MAX_DISCUSSION_MARKS) return undefined;
  const parsed: DiscussionMark[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return undefined;
    const mark = item as Record<string, unknown>;
    if (
      Object.keys(mark).some(
        (key) => !['id', 'orientation', 'color', 'author', 'points_lps_mm'].includes(key),
      ) ||
      typeof mark.id !== 'string' ||
      !markIdPattern.test(mark.id) ||
      !orientations.has(mark.orientation as MprOrientation) ||
      typeof mark.color !== 'string' ||
      !(mark.color in DISCUSSION_MARK_COLORS) ||
      (mark.author !== 'person' && mark.author !== 'agent') ||
      !Array.isArray(mark.points_lps_mm) ||
      mark.points_lps_mm.length < 1 ||
      mark.points_lps_mm.length > MAX_DISCUSSION_MARK_POINTS
    ) {
      return undefined;
    }
    const points = mark.points_lps_mm.map(patientPoint);
    if (points.some((point) => !point)) return undefined;
    parsed.push({
      id: mark.id,
      orientation: mark.orientation as MprOrientation,
      color: mark.color as DiscussionMarkColor,
      author: mark.author,
      points_lps_mm: points as MprPatientPoint[],
    });
  }
  if (new Set(parsed.map((mark) => mark.id)).size !== parsed.length) return undefined;
  return parsed;
};

export const roundedPatientPoint = (point: MprPatientPoint): MprPatientPoint =>
  point.map((coordinate) => Math.round(coordinate * 100) / 100) as MprPatientPoint;

export const discussionMarksAfterCommand = (
  current: DiscussionMark[],
  commanded?: DiscussionMark[],
): DiscussionMark[] => commanded ?? current;

export const discussionOrientationForImage = (
  imageOrientationPatient?: number[],
): MprOrientation | undefined => {
  if (
    imageOrientationPatient?.length !== 6 ||
    !imageOrientationPatient.every(Number.isFinite)
  ) {
    return undefined;
  }
  const row = imageOrientationPatient.slice(0, 3);
  const column = imageOrientationPatient.slice(3, 6);
  const normal = [
    row[1] * column[2] - row[2] * column[1],
    row[2] * column[0] - row[0] * column[2],
    row[0] * column[1] - row[1] * column[0],
  ];
  const dominantAxis = normal
    .map(Math.abs)
    .reduce((best, value, axis, values) => (value > values[best] ? axis : best), 0);
  return dominantAxis === 0 ? 'sagittal' : dominantAxis === 1 ? 'coronal' : 'axial';
};
