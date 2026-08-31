export type ReadyStatus = {
  status: "ready";
};

export async function getReadyStatus(
  signal?: AbortSignal,
): Promise<ReadyStatus> {
  const response = await fetch("/api/health/ready", {
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(
      `Backend readiness failed with HTTP ${response.status}`,
    );
  }

  return response.json() as Promise<ReadyStatus>;
}
