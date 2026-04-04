'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import Script from 'next/script';
import { useMemo, useState } from 'react';
import { AlertCircle, ArrowLeft, Box, Download, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { useCreateTryOn3DJob, useTryOn3DJob } from '@/lib/hooks/use-tryon3d';

export default function Pairing3DPage({ params }: { params: { pairingId: string } }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pairingId = params.pairingId;
  const jobId = searchParams.get('jobId') || undefined;

  const { data: job, isLoading } = useTryOn3DJob(pairingId, jobId);
  const createTryOn = useCreateTryOn3DJob();
  const [viewerError, setViewerError] = useState<string | null>(null);

  const cacheBuster = useMemo(() => {
    if (!job?.updated_at) return Date.now().toString();
    return new Date(job.updated_at).getTime().toString();
  }, [job?.updated_at]);

  const proxyAssetUrl = (fmt: 'glb' | 'fbx' | 'usdz', download = false) => {
    if (!job?.id) return '#';
    const base = `/api/tryon-asset/${pairingId}/${job.id}/${fmt}`;
    return download ? `${base}?download=1&v=${cacheBuster}` : `${base}?v=${cacheBuster}`;
  };

  const handleRetry = async () => {
    try {
      const newJob = await createTryOn.mutateAsync({ outfitId: pairingId });
      router.replace(`/dashboard/pairings/${pairingId}/3d?jobId=${newJob.id}`);
    } catch {
      // handled by status/error state below on next poll attempt
    }
  };

  if (!jobId) {
    return (
      <div className="space-y-4">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>No 3D job selected. Start from the Pairings page.</AlertDescription>
        </Alert>
        <Button asChild variant="outline">
          <Link href="/dashboard/pairings">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Pairings
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Script
        type="module"
        src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"
      />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Box className="h-6 w-6 text-primary" />
            Pairing 3D Model
          </h1>
          <p className="text-muted-foreground">Generate and download a 3D model for this pairing.</p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/dashboard/pairings">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {isLoading || !job ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading status...
              </>
            ) : (
              <>
                <span>Status</span>
                <Badge variant={job.status === 'completed' ? 'default' : job.status === 'failed' ? 'destructive' : 'secondary'}>
                  {job.status}
                </Badge>
              </>
            )}
          </CardTitle>
          <CardDescription>
            Job ID: {jobId}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {job && (
            <>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div className="p-2 rounded border">Fashn: <span className="font-medium">{job.step_status?.fashn || 'queued'}</span></div>
                <div className="p-2 rounded border">Gemini: <span className="font-medium">{job.step_status?.gemini || 'queued'}</span></div>
                <div className="p-2 rounded border">Meshy: <span className="font-medium">{job.step_status?.meshy || 'queued'}</span></div>
              </div>

              {job.error && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{job.error}</AlertDescription>
                </Alert>
              )}

              {job.gemini_texture_prompt && (
                <div className="p-3 rounded border bg-muted/40">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Gemini texture prompt</p>
                  <p className="text-sm">{job.gemini_texture_prompt}</p>
                </div>
              )}

              {job.status === 'completed' && (
                <div className="space-y-2">
                  {job.glb_url && (
                    <div className="rounded border overflow-hidden bg-muted/20">
                      <model-viewer
                        src={proxyAssetUrl('glb')}
                        poster={job.fashn_result_image_url}
                        camera-controls
                        auto-rotate
                        shadow-intensity="1"
                        onLoad={() => setViewerError(null)}
                        onError={() => setViewerError('3D preview failed to load. Try downloading the GLB and reloading the page.')}
                        style={{ width: '100%', height: '460px', background: 'transparent' }}
                      />
                    </div>
                  )}
                  {viewerError && (
                    <Alert variant="destructive">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>{viewerError}</AlertDescription>
                    </Alert>
                  )}
                  <p className="text-sm font-medium">Downloads</p>
                  <div className="flex flex-wrap gap-2">
                    {job.glb_url && (
                      <Button asChild variant="outline" size="sm">
                        <a href={proxyAssetUrl('glb', true)} target="_blank" rel="noreferrer">
                          <Download className="h-4 w-4 mr-2" />
                          GLB
                        </a>
                      </Button>
                    )}
                    {job.fbx_url && (
                      <Button asChild variant="outline" size="sm">
                        <a href={proxyAssetUrl('fbx', true)} target="_blank" rel="noreferrer">
                          <Download className="h-4 w-4 mr-2" />
                          FBX
                        </a>
                      </Button>
                    )}
                    {job.usdz_url && (
                      <Button asChild variant="outline" size="sm">
                        <a href={proxyAssetUrl('usdz', true)} target="_blank" rel="noreferrer">
                          <Download className="h-4 w-4 mr-2" />
                          USDZ
                        </a>
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          <div className="pt-2">
            <Button onClick={handleRetry} disabled={createTryOn.isPending || job?.status === 'running' || job?.status === 'queued'}>
              {createTryOn.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Retry Generation
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
