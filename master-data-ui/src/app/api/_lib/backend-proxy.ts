import "server-only";
import { NextRequest, NextResponse } from "next/server";
import { getBackendConfig } from "./backend-config";
import { BackendResponse, RequestBody } from "./backend-types";
import { createBackendRequest } from "./backend-request";
import { requireAuth } from "./requireAuth";
import { applyBackendSetCookies } from "./auth-cookies";

export type PayloadBuilder = (body: any) => RequestBody;
export type ResponseTransformer = (responseBody: any) => any;

interface BackendProxyOptions {
	req: NextRequest;
	targetEndpoint: string; // Backend API endpoint
	buildPayload?: PayloadBuilder;
	transformResponse?: ResponseTransformer; // Transforms backend response for client
	caching?: RequestInit; // this is used for Nextjs caching
	responseHeaders?: HeadersInit; // HTTP headers for client response or caching
}

const errorCodeMap: Record<string, number> = {
	"G2P-REQ-400": 400, // Bad Request
	"G2P-AUT-401": 401, // Unauthorized
	"G2P-AUT-403": 403, // Forbidden
	"G2P-REQ-404": 404, // Resource Not Found
	"G2P-AUT-404": 404, // Authentication Not Found
	"G2P-REQ-405": 405, // Method Not Allowed
	"G2P-REQ-500": 500, // Internal Server Error
};


export async function proxyToBackend({
	req,
	targetEndpoint,
	buildPayload,
	transformResponse,
	caching,
	responseHeaders
}: BackendProxyOptions) {

	const backendConfig = getBackendConfig()
	const auth = requireAuth(req);
	if (auth instanceof NextResponse) return auth;

	const backendUrl = `${backendConfig.backendUrl}${targetEndpoint}`;

	try {
		const contentType = req.headers.get("content-type") || "";
		const isFormData = contentType.includes("multipart/form-data");

		let body: any = {};
		if (req.method !== 'GET') {
			if (isFormData) {
				body = await req.formData();
			} else {
				try {
					body = await req.json();
				} catch (e) {
					// ignore JSON parse error for empty body or if already read
				}
			}
		}

		const fetchOptions: RequestInit = {
			method: "POST",
			...caching,
		};

		if (isFormData) {
			const { 'content-type': _, 'Content-Type': __, ...cleanHeaders } =
				auth.backendHeaders as Record<string, string>;

			fetchOptions.headers = {
				...cleanHeaders,
			};
			fetchOptions.body = body;
			// When sending FormData, the browser/runtime will automatically set
			// the Content-Type header with the correct boundary.
		}
		else {
			const defaultPayloadBuilder: PayloadBuilder = (b) => ({
				pagination_request: undefined,
				request_payload: b
			});

			const payload = (buildPayload || defaultPayloadBuilder)(body);

			const h = req.headers;
			const host = h.get("x-forwarded-host") || h.get("host");
			const proto = h.get("x-forwarded-proto") || "https";
			const origin = h.get("origin") || `${proto}://${host}`;

			const backendRequest = createBackendRequest(payload, origin);

			fetchOptions.headers = {
				...auth.backendHeaders,
				"Content-Type": "application/json",
			};
			fetchOptions.body = JSON.stringify(backendRequest);
		}

		const response = await fetch(backendUrl, fetchOptions);

		if (!response.ok) {
			return NextResponse.json(
				{ statusText: response.statusText, code: response.status },
				{ status: response.status, headers: responseHeaders },
			);
		}

		const backendResponse: BackendResponse = await response.json();

		if (backendResponse.response_header?.response_status === 'ERROR') {
			const header = backendResponse.response_header;
			const errorCode = header.response_error_code;
			const httpStatus = errorCodeMap[errorCode] ?? 400;
			const errorMessage = header.response_error_message || 'Something went wrong';

			const errorResponse = NextResponse.json(
				{ statusText: errorMessage,code: errorCode},
				{ status: httpStatus, headers: responseHeaders },
			);

			applyBackendSetCookies(response, errorResponse);
			return errorResponse;
		}

		const responseBody = backendResponse.response_body;
		const data = transformResponse
			? transformResponse(responseBody)
			: responseBody?.response_payload;

		if (data === undefined) {
			const emptyResponse = NextResponse.json(
				{ statusText: 'Empty response from backend', code: 200 },
				{ status: 200, headers: responseHeaders },
			);
			applyBackendSetCookies(response, emptyResponse);
			return emptyResponse;
		}

		const successResponse = NextResponse.json(data, {
			status: 200,
			headers: responseHeaders,
		});
		applyBackendSetCookies(response, successResponse);
		return successResponse;

	} catch (e) {
		return NextResponse.json(
			{ statusText: e instanceof Error ? e.message : 'Internal Server Error', code: 500 },
			{ status: 500 },
		);
	}
}
