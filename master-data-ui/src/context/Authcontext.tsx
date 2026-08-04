'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';

interface AuthContextType {
    isLoggedIn: boolean;
    user: any | null;
    logout: () => void;
    handleUnauthorized: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [user, setUser] = useState<any | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [errorCode, setErrorCode] = useState<string | null>(null);
    const t = useTranslations();

    const logout = useCallback(() => {
        setIsLoggedIn(false);
        setUser(null);
        window.location.href = '/api/logout';
    }, []);

    const handleUnauthorized = useCallback(() => {
        setIsLoggedIn(false);
        setUser(null);
        window.location.href = `/api/login?redirect_uri=${encodeURIComponent(window.location.href)}`;
    }, []);

    useEffect(() => {
        async function initAuth() {
            try {
                const res = await fetch("/api/me");

                if (res.status === 401) {
                    let error: any = {};
                    try {
                        error = await res.json();
                    } catch { }

                    const errorObj = error?.errors?.[0] || {};
                    const code =
                        errorObj.code ||
                        error?.response_header?.response_error_code ||
                        error?.code;
                    const message = (
                        errorObj.message ||
                        error?.response_header?.response_error_message ||
                        error?.error ||
                        ""
                    ).toLowerCase();

                    if (
                        message.includes("expired") ||
                        message.includes("invalid jwt") ||
                        message.includes("inactive token") ||
                        message.includes("session has ended") ||
                        message.includes("refresh failed") ||
                        code === 'G2P-AUT-LOGIN-REQUIRED'
                    ) {
                        handleUnauthorized();
                        return;
                    }

                    setErrorCode("AUTH_GENERIC_ERROR");
                    return;
                }

                if (res.status === 413) {
                    setErrorCode('G2P-AUT-413');
                    return;
                }

                if (res.status === 403) {
                    setErrorCode('G2P-AUT-403');
                    return;
                }

                const data = await res.json();

                if (res.ok) {
                    setUser(data);
                    setIsLoggedIn(true);
                } else {
                    console.log(data);
                }

            } catch (err) {
                console.error("Request failed:", err);
            } finally {
                setIsLoading(false);
            }
        }

        initAuth();
    }, []);

    if (isLoading) {
        return (
            <div className="w-full min-h-screen flex items-center justify-center bg-neutral-second">
                <div className="flex flex-col items-center gap-4">
                    <img
                        src="/images/common/loading.gif"
                        alt="Loading"
                        className="w-12 h-12"
                    />
                    <p className="text-neutral-first/50 text-[20px]">{t('loading')}</p>
                </div>
            </div>
        );
    }

    if (errorCode === 'AUTH_GENERIC_ERROR') {
        return (
            <div className="w-full min-h-screen flex items-center justify-center bg-secondary-first px-4">
                <div className="bg-neutral-second drop-shadow-lg rounded-lg p-10 max-w-150 w-full text-center">
                    <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-6">
                        <svg className="w-7 h-7 text-toast-failed" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                        </svg>
                    </div>

                    <h1 className="text-2xl font-semibold text-neutral-first">{t('generic_error_title')}</h1>
                    <p className="text-neutral-first mt-4 text-lg leading-relaxed">
                        {t('generic_error_description')}
                    </p>
                </div>
            </div>
        );
    }

    if (errorCode === 'G2P-AUT-413') {
        return (
            <div className="w-full min-h-screen flex items-center justify-center bg-secondary-first px-4">
                <div className="bg-neutral-second drop-shadow-[0_4px_20px_rgba(0,0,0,0.25)] rounded-[10px] p-10 max-w-180 w-full text-center">

                    <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-6">
                        <svg className="w-7 h-7 text-toast-failed" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                        </svg>
                    </div>

                    <h1 className="text-2xl font-semibold text-neutral-first">
                        {t('token_size_title')}
                    </h1>

                    <p className="text-neutral-first mt-4 text-lg leading-relaxed">
                        {t('token_size_description')}
                    </p>

                    <p className="text-neutral-first mt-2 text-base leading-relaxed">
                        {t('token_size_cause')}
                    </p>

                    <div className="mt-6 text-left bg-neutral-second border border-black/20 rounded-[10px] p-5">
                        <p className="text-base font-semibold text-neutral-first mb-3">
                            {t('required_action')}
                        </p>

                        <ol className="space-y-3">
                            {[
                                t('step_reduce_roles'),
                                t('step_optimize_claims'),
                                t('step_reissue_token'),
                            ].map((step, i) => (
                                <li key={i} className="flex items-start gap-3">
                                    <span className="w-6 h-6 rounded-full bg-neutral-first text-neutral-second text-xs font-semibold flex items-center justify-center shrink-0 mt-0.5">
                                        {i + 1}
                                    </span>
                                    <span className="text-base text-neutral-first">{step}</span>
                                </li>
                            ))}
                        </ol>
                    </div>

                    <p className="text-[16px] font-bold text-neutral-first mt-4">
                        Error Code: <span className="font-mono">G2P-AUT-413</span>
                    </p>
                </div>
            </div>
        );
    }

    if (errorCode === 'G2P-AUT-403') {
        return (
            <div className="w-full min-h-screen flex items-center justify-center bg-neutral-second px-4">
                <div className="flex flex-1 items-center justify-start">
                    <div className="w-full bg-neutral-second rounded-[10px] flex flex-col items-center text-center">
                        <Image
                            src="/images/common/forbidden.png"
                            width={140}
                            height={140}
                            alt="Forbidden illustration"
                            className="mb-6"
                            priority
                        />

                        <h1 className="mb-4 text-[40px] font-semibold leading-11.75 text-primary-second">
                            {t('access_denied')}
                        </h1>

                        <p className="mb-6 text-[20px] font-light leading-6 text-neutral-first/50 max-w-xl">
                            {t('no_permission')}
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    if (!isLoggedIn) return null;

    return (
        <AuthContext.Provider value={{ isLoggedIn, user, logout, handleUnauthorized }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
    return ctx;
}