import createMiddleware from 'next-intl/middleware';
import { NextRequest } from 'next/server';

import { getServerEnv } from '@/app/api/_lib/env-config';
import { routing } from './i18n/routing';

export default function middleware(request: NextRequest) {
    const env = getServerEnv();
    const defaultLocale = env.defaultLocale || routing.defaultLocale;
    const handleRequest = createMiddleware({
        ...routing,
        defaultLocale: defaultLocale as any,
    });

    return handleRequest(request);
}

export const config = {
    matcher: ['/((?!api|_next|.*\\..*).*)'],
};
