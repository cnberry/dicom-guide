import type { MprPatientPoint } from './mpr';

type PatientPointController = {
  setPatientPoint: (point: MprPatientPoint) => void;
};

export const applyRequestedPatientPoint = (
  controller: PatientPointController,
  requestedPoint: MprPatientPoint,
  publishAppliedPoint: (point: MprPatientPoint) => void,
): void => {
  const appliedPoint = [...requestedPoint] as MprPatientPoint;
  controller.setPatientPoint(appliedPoint);
  publishAppliedPoint(appliedPoint);
};
