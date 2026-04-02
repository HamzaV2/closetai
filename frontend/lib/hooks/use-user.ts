'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api, setAccessToken } from '@/lib/api';

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  timezone: string;
  location_lat?: number;
  location_lon?: number;
  location_name?: string;
  family_id?: string;
  role: string;
  onboarding_completed: boolean;
  tryon_model_image_url?: string;
}

export interface UserProfileUpdate {
  display_name?: string;
  timezone?: string;
  location_lat?: number;
  location_lon?: number;
  location_name?: string;
}

function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export function useUserProfile() {
  const { status } = useSession();
  useSetTokenIfAvailable();

  return useQuery({
    queryKey: ['user-profile'],
    queryFn: () => api.get<UserProfile>('/users/me'),
    enabled: status !== 'loading',
  });
}

export function useUpdateUserProfile() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (data: UserProfileUpdate) => {
      if (session?.accessToken) {
        setAccessToken(session.accessToken as string);
      }
      return api.patch<UserProfile>('/users/me', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
    },
  });
}

export function useUploadTryOnModelImage() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();

  return useMutation({
    mutationFn: async (file: File) => {
      const token = session?.accessToken as string | undefined;
      const formData = new FormData();
      formData.append('image', file);
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const response = await fetch('/api/v1/users/me/tryon-model-image', {
        method: 'POST',
        body: formData,
        headers,
        credentials: 'include',
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to upload try-on model image');
      }
      return response.json() as Promise<UserProfile>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
    },
  });
}

export function useDeleteTryOnModelImage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<UserProfile>('/users/me/tryon-model-image'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
    },
  });
}
