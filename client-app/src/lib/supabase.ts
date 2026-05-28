import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase = createClient(
  supabaseUrl || 'https://placeholder.supabase.co',
  supabaseAnonKey || 'placeholder-anon-key',
  {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  },
);

export function assertSupabaseConfigured(): void {
  if (!isSupabaseConfigured) {
    throw new Error('Variables VITE_SUPABASE_URL et VITE_SUPABASE_ANON_KEY requises.');
  }
}

export async function invokeFunction<T>(
  name: string,
  options: {
    body?: BodyInit | Record<string, unknown> | null;
    method?: 'GET' | 'POST' | 'DELETE';
  } = {},
): Promise<T> {
  assertSupabaseConfigured();
  const invokeOptions: { body?: BodyInit | Record<string, unknown>; method: 'GET' | 'POST' | 'DELETE' } = {
    method: options.method ?? 'POST',
  };
  if (options.body != null) invokeOptions.body = options.body;
  const { data, error } = await supabase.functions.invoke<T>(name, invokeOptions);
  if (error) {
    const context = (error as { context?: unknown }).context;
    if (context instanceof Response) {
      const text = await context.text().catch(() => '');
      const payload = parseFunctionErrorPayload(text);
      if (payload) {
        throw new Error(payload.error ?? payload.message ?? error.message);
      } else {
        if (text) throw new Error(text);
      }
    }
    throw new Error(error.message);
  }
  return data as T;
}

function parseFunctionErrorPayload(text: string): { error?: string; message?: string; details?: unknown } | null {
  try {
    return JSON.parse(text) as { error?: string; message?: string; details?: unknown };
  } catch {
    return null;
  }
}

export async function fetchFunctionBlob(
  name: string,
  method: 'GET' | 'POST' | 'DELETE' = 'GET',
): Promise<Blob> {
  assertSupabaseConfigured();
  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token;
  if (!token) throw new Error('Session Supabase requise.');

  const response = await fetch(`${supabaseUrl}/functions/v1/${name}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      apikey: supabaseAnonKey || '',
    },
  });
  if (!response.ok) throw new Error(await response.text());
  return await response.blob();
}
