// Single source of server/runtime env — read at request time (K8s pod env, not Docker build).
export function getServerEnv() {
    return {
        masterdataBackendApiUrl: process.env.MASTERDATA_BACKEND_API_URL ?? "",
        iamUrl: process.env.IAM_URL ?? "",
        loginProviderId: process.env.LOGIN_PROVIDER_ID ?? "",
        applicationMnemonic: process.env.APPLICATION_MNEMONIC ?? "openg2p-master-data",
        cookieDomain: process.env.COOKIE_DOMAIN?.trim() ?? "",
        defaultLocale: process.env.DEFAULT_LOCALE ?? "",
    };
}

export type ServerEnv = ReturnType<typeof getServerEnv>;
