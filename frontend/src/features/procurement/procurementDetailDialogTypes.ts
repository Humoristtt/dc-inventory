export type ProcurementAction = (
  action: string,
  extra?: Record<string, unknown>,
) => void;
