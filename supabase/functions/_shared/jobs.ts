import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export async function createJob(
  client: SupabaseClient,
  userId: string,
  type: string,
  payload: Record<string, unknown> = {},
): Promise<string | null> {
  const { data, error } = await client
    .from("sync_jobs")
    .insert({
      user_id: userId,
      type,
      status: "running",
      progress: 0,
      stage: "start",
      payload,
      started_at: new Date().toISOString(),
    })
    .select("id")
    .single();

  if (error) throw error;
  return data?.id ?? null;
}

export async function updateJob(
  client: SupabaseClient,
  jobId: string | null,
  patch: Record<string, unknown>,
): Promise<void> {
  if (!jobId) return;
  const { error } = await client
    .from("sync_jobs")
    .update(patch)
    .eq("id", jobId);
  if (error) throw error;
}

export async function addJobEvent(
  client: SupabaseClient,
  jobId: string | null,
  userId: string,
  type: string,
  message?: string,
  payload: Record<string, unknown> = {},
): Promise<void> {
  if (!jobId) return;
  const { error } = await client.from("job_events").insert({
    job_id: jobId,
    user_id: userId,
    type,
    message,
    payload,
  });
  if (error) throw error;
}
