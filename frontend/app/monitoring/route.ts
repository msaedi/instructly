import { NextResponse } from 'next/server';

const EMPTY_RESPONSE = new NextResponse(null, { status: 204 });

export function GET() {
  return EMPTY_RESPONSE;
}

export function HEAD() {
  return EMPTY_RESPONSE;
}
