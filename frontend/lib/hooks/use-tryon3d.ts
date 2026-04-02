'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';

import { api, setAccessToken } from '@/lib/api';

export interface TryOn3DJob {
  id: string;
  outfit_id: string;
  status: 'queued' | 'running' | 'failed' | 'completed';
  step_status: Record<string, string>;
  error: string | null;
  fashn_result_image_url?: string;
  gemini_texture_prompt?: string;
  glb_url?: string;
  fbx_url?: string;
  usdz_url?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

function useSetTokenIfAvailable() {
  const { data: session } = useSession();
  if (session?.accessToken) {
    setAccessToken(session.accessToken as string);
  }
}

export function useCreateTryOn3DJob() {
  const queryClient = useQueryClient();
  useSetTokenIfAvailable();

  return useMutation({
    mutationFn: ({ outfitId, userPrompt }: { outfitId: string; userPrompt?: string }) =>
      api.post<TryOn3DJob>(`/outfits/${outfitId}/tryon-3d`, { user_prompt: userPrompt || '' }),
    onSuccess: (_, { outfitId }) => {
      queryClient.invalidateQueries({ queryKey: ['tryon3d', outfitId] });
    },
  });
}

export function useTryOn3DJob(outfitId: string | undefined, jobId: string | undefined) {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: ['tryon3d', outfitId, jobId],
    queryFn: () => api.get<TryOn3DJob>(`/outfits/${outfitId}/tryon-3d/${jobId}`),
    enabled: !!outfitId && !!jobId && status !== 'loading',
    refetchInterval: (query) => {
      const data = query.state.data as TryOn3DJob | undefined;
      if (!data) return 2000;
      return data.status === 'queued' || data.status === 'running' ? 3000 : false;
    },
  });
}
