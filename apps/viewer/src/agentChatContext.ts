import { normalFromOrientation, type DicomSeries } from './dicom';
import type { MprPatientPoint } from './mpr';

export type AgentChatViewMode = 'native' | 'mpr';

export type AgentChatContext = {
  schema_version: '1.0.0';
  view_mode: AgentChatViewMode;
  series_id: string;
  instance_id: string;
  stack_position: number;
  stack_count: number;
  modality: string;
  acquisition_date: string;
  patient_point_lps_mm: MprPatientPoint | null;
  pointer_source: 'cursor' | 'mpr_crosshair' | 'none';
  privacy: {
    local_only: true;
    contains_pixels: false;
    contains_direct_identifiers: false;
    contains_source_text: false;
    deidentified: false;
    persisted: false;
  };
};

export const buildAgentChatContext = ({
  series,
  index,
  viewMode,
  patientPoint,
}: {
  series?: DicomSeries;
  index: number;
  viewMode: AgentChatViewMode;
  patientPoint?: MprPatientPoint;
}): AgentChatContext | undefined => {
  if (!series || !Number.isInteger(index) || index < 0 || index >= series.instances.length) {
    return undefined;
  }
  const point =
    patientPoint?.length === 3 && patientPoint.every(Number.isFinite)
      ? ([...patientPoint] as MprPatientPoint)
      : null;
  let resolvedIndex = index;
  if (viewMode === 'mpr' && point) {
    const normal = normalFromOrientation(series.geometry.orientation);
    if (normal && series.instances.every((item) => item.imagePosition?.length === 3)) {
      const targetProjection = point.reduce(
        (sum, value, axis) => sum + value * normal[axis],
        0,
      );
      resolvedIndex = series.instances.reduce((closest, item, itemIndex) => {
        const projection = item.imagePosition!.reduce(
          (sum, value, axis) => sum + value * normal[axis],
          0,
        );
        const closestProjection = series.instances[closest].imagePosition!.reduce(
          (sum, value, axis) => sum + value * normal[axis],
          0,
        );
        return Math.abs(projection - targetProjection) <
          Math.abs(closestProjection - targetProjection)
          ? itemIndex
          : closest;
      }, 0);
    }
  }
  const instance = series.instances[resolvedIndex];
  return {
    schema_version: '1.0.0',
    view_mode: viewMode,
    series_id: series.id,
    instance_id: instance.instanceId,
    stack_position: resolvedIndex + 1,
    stack_count: series.instances.length,
    modality: series.modality,
    acquisition_date: series.acquisitionDate ?? '',
    patient_point_lps_mm: point,
    pointer_source: point ? (viewMode === 'mpr' ? 'mpr_crosshair' : 'cursor') : 'none',
    privacy: {
      local_only: true,
      contains_pixels: false,
      contains_direct_identifiers: false,
      contains_source_text: false,
      deidentified: false,
      persisted: false,
    },
  };
};
