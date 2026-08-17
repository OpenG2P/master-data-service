import { defineRouting } from 'next-intl/routing';

export const routing = defineRouting({
    locales: ['en', 'es', 'fr', 'am', 'ar','hi'],
    defaultLocale: 'en'
});
