import { NextRequest, NextResponse } from 'next/server';
import { getToken } from 'next-auth/jwt';

const BACKEND_URL =
  process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000';

type Params = {
  outfitId: string;
  jobId: string;
  fmt: string;
};

export async function GET(
  req: NextRequest,
  { params }: { params: Params }
) {
  const token = await getToken({ req, secret: process.env.NEXTAUTH_SECRET });
  const accessToken = token?.accessToken as string | undefined;

  if (!accessToken) {
    return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 });
  }

  const fmt = params.fmt.toLowerCase();
  if (!['glb', 'fbx', 'usdz'].includes(fmt)) {
    return NextResponse.json({ detail: 'Invalid format' }, { status: 400 });
  }

  const upstream = `${BACKEND_URL}/api/v1/outfits/${params.outfitId}/tryon-3d/${params.jobId}/asset/${fmt}`;
  const upstreamRes = await fetch(upstream, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    cache: 'no-store',
  });

  if (!upstreamRes.ok) {
    const text = await upstreamRes.text().catch(() => '');
    return new NextResponse(text || 'Failed to fetch asset', { status: upstreamRes.status });
  }

  const bytes = await upstreamRes.arrayBuffer();
  const mediaType =
    upstreamRes.headers.get('content-type') ||
    (fmt === 'glb'
      ? 'model/gltf-binary'
      : fmt === 'usdz'
        ? 'model/vnd.usdz+zip'
        : 'application/octet-stream');

  const download = req.nextUrl.searchParams.get('download') === '1';
  const filename = `pairing-tryon-${params.jobId}.${fmt}`;

  const headers = new Headers();
  headers.set('content-type', mediaType);
  headers.set(
    'content-disposition',
    `${download ? 'attachment' : 'inline'}; filename="${filename}"`
  );

  return new NextResponse(bytes, { status: 200, headers });
}
