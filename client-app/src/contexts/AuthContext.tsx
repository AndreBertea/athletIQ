import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  fullName: string;
}

export interface AuthContextValue {
  user: AuthUser | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function deriveDisplayName(email: string, fullName: string | null | undefined): string {
  const trimmed = (fullName ?? '').trim();
  if (trimmed) return trimmed;
  const local = email.split('@')[0] ?? '';
  return local ? local.charAt(0).toUpperCase() + local.slice(1) : 'Athlète';
}

function fullNameFromEmail(email: string): string {
  return deriveDisplayName(email, null);
}

function mapUser(user: User): AuthUser {
  const email = user.email ?? '';
  const fullName = typeof user.user_metadata?.full_name === 'string'
    ? user.user_metadata.full_name
    : '';

  return {
    id: user.id,
    email,
    fullName,
    displayName: deriveDisplayName(email, fullName),
  };
}

async function upsertProfile(user: User, fullName?: string): Promise<void> {
  const email = user.email ?? '';
  const resolvedFullName = fullName ?? (typeof user.user_metadata?.full_name === 'string'
    ? user.user_metadata.full_name
    : fullNameFromEmail(email));

  await supabase.from('profiles').upsert({
    id: user.id,
    email,
    full_name: resolvedFullName,
    display_name: deriveDisplayName(email, resolvedFullName),
  });
}

function humanReadableAuthError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  if (/invalid login credentials/i.test(message)) return 'Email ou mot de passe incorrect.';
  if (/already registered|already exists|user already/i.test(message)) return 'Un compte existe déjà pour cet email.';
  if (/password/i.test(message)) return 'Mot de passe invalide ou trop court.';
  return message || 'Connexion impossible. Réessaie dans un instant.';
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setUser(data.session?.user ? mapUser(data.session.user) : null);
      setIsLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ? mapUser(session.user) : null);
      setIsLoading(false);
    });

    return () => {
      mounted = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    if (error) throw new Error(humanReadableAuthError(error));
    if (data.user) await upsertProfile(data.user);
  }, []);

  const signUp = useCallback(async (email: string, password: string) => {
    const trimmed = email.trim();
    const fullName = fullNameFromEmail(trimmed);
    const { data, error } = await supabase.auth.signUp({
      email: trimmed,
      password,
      options: {
        data: { full_name: fullName },
      },
    });
    if (error) throw new Error(humanReadableAuthError(error));
    if (data.user) await upsertProfile(data.user, fullName);
  }, []);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, signIn, signUp, signOut, isLoading }),
    [user, signIn, signUp, signOut, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth() doit être utilisé dans <AuthProvider>');
  return ctx;
}
