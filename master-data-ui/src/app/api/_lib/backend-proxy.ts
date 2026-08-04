import { NextRequest, NextResponse } from "next/server";
import { getBackendConfig } from "./backend-config";
import { requireAuth } from "./requireAuth";
import { applyBackendSetCookies } from "./auth-cookies";
import { createBackendRequest } from "./backend-request";
import type { BackendResponse, RequestBody } from "./backend-types";

export type PayloadBuilder = (body: Record<string, unknown>) => RequestBody;

interface BackendProxyOptions {
    req: NextRequest;
    targetEndpoint: string;
    buildPayload?: PayloadBuilder;
}

const ERROR_CODE_STATUS: Record<string, number> = {
    "G2P-AUT-401": 401,
    "G2P-AUT-403": 403,
    "G2P-AUT-404": 404,
};

export async function proxyToBackend({
    req,
    targetEndpoint,
    buildPayload,
}: BackendProxyOptions): Promise<NextResponse> {
    const auth = requireAuth(req);
    if (auth instanceof NextResponse) return auth;

    const backendConfig = getBackendConfig();
    const backendUrl = `${backendConfig.masterdataBackendApiUrl}${targetEndpoint}`;

    let body: Record<string, unknown> = {};
    try {
        body = await req.json();
    } catch {
        // empty or non-JSON body — leave as {}
    }

    const h = req.headers;
    const host = h.get("x-forwarded-host") || h.get("host") || "";
    const proto = h.get("x-forwarded-proto") || "https";
    const origin = h.get("origin") || `${proto}://${host}`;

    const defaultPayload: PayloadBuilder = (b) => ({
        pagination_request: undefined,
        request_payload: b,
    });

    const payload = (buildPayload ?? defaultPayload)(body);
    const backendRequest = createBackendRequest(payload, origin);

    let response: Response;
    try {
        response = await fetch(backendUrl, {
            method: "POST",
            headers: {
                ...auth.backendHeaders,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(backendRequest),
        });
    } catch (err) {
        return NextResponse.json(
            { error: err instanceof Error ? err.message : "Network error" },
            { status: 502 }
        );
    }

    const backendResponse: BackendResponse = await response.json();

    if (backendResponse.response_header?.response_status === "ERROR") {
        const errorCode = backendResponse.response_header.response_error_code;
        const status = ERROR_CODE_STATUS[errorCode] ?? 400;
        const errorRes = NextResponse.json(
            {
                error: backendResponse.response_header.response_error_message,
                code: errorCode,
            },
            { status }
        );
        applyBackendSetCookies(response, errorRes);
        return errorRes;
    }

    const data = backendResponse.response_body?.response_payload;
    if (data === undefined) {
        return NextResponse.json({ error: "Empty response from backend" }, { status: 500 });
    }

    const successRes = NextResponse.json(data);
    applyBackendSetCookies(response, successRes);
    return successRes;
}
