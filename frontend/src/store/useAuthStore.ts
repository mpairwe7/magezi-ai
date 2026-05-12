import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  credits: number;
  has_api_key: boolean;
  plan: string;
}

const noopStorage: Storage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
  clear: () => {},
  key: () => null,
  length: 0,
};

interface AuthStore {
  token: string | null;
  user: UserProfile | null;
  setAuth: (token: string, user: UserProfile) => void;
  updateUser: (user: UserProfile) => void;
  updateCredits: (credits: number) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      updateUser: (user) => set({ user }),
      updateCredits: (credits) =>
        set((s) => s.user ? { user: { ...s.user, credits } } : s),
      logout: () => set({ token: null, user: null }),
    }),
    {
      name: 'magezi-auth',
      storage: createJSONStorage(() => {
        if (typeof window === 'undefined') return noopStorage;
        return localStorage;
      }),
    },
  ),
);
