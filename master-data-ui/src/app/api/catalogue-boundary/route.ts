import { randomUUID } from "crypto";
import { NextRequest, NextResponse } from "next/server";
import { getBackendConfig } from "@/app/api/_lib/backend-config";
import { getServerEnv } from "@/app/api/_lib/env-config";
import { requireAuth } from "@/app/api/_lib/requireAuth";
import { applyBackendSetCookies } from "@/app/api/_lib/auth-cookies";

/**
 * Download a level's boundary GeoJSON of a geography version:
 * `GET /api/catalogue-boundary?level=<mnemonic>&version=<n|latest|draft>`.
 * Calls `/catalogue/get_geo_boundary` with `stream: true` and returns the GeoJSON as an attachment.
 */
export async function GET(req: NextRequest) {
	const auth = requireAuth(req);
	if (auth instanceof NextResponse) return auth;

	const level = req.nextUrl.searchParams.get("level")?.trim();
	const rawVersion = req.nextUrl.searchParams.get("version")?.trim() || "latest";
	if (!level) {
		return NextResponse.json({ statusText: "level is required", code: "G2P-REQ-400" }, { status: 400 });
	}
	const version =
		rawVersion === "latest" || rawVersion === "draft"
			? rawVersion
			: Number.isInteger(Number(rawVersion))
				? Number(rawVersion)
				: null;
	if (version === null) {
		return NextResponse.json({ statusText: "invalid version", code: "G2P-REQ-400" }, { status: 400 });
	}

	const h = req.headers;
	const host = h.get("x-forwarded-host") || h.get("host");
	const proto = h.get("x-forwarded-proto") || "https";
	const origin = `${proto}://${host}`;

	const backendRequest = {
		request_header: {
			sender_app_mnemonic: getServerEnv().applicationMnemonic,
			sender_app_url: origin,
			request_id: randomUUID(),
			request_timestamp: new Date().toISOString(),
		},
		request_body: { request_payload: { level, version, stream: true } },
	};

	try {
		const res = await fetch(`${getBackendConfig().backendUrl}/catalogue/get_geo_boundary`, {
			method: "POST",
			headers: { ...auth.backendHeaders, "Content-Type": "application/json" },
			body: JSON.stringify(backendRequest),
			cache: "no-store",
		});
		const contentType = res.headers.get("content-type") || "";
		if (!res.ok || contentType.includes("application/json")) {
			// The envelope (an error) instead of GeoJSON.
			let message = res.statusText || "Boundary not available";
			try {
				const body = await res.json();
				message = body?.response_header?.response_error_message || message;
			} catch {
				// keep statusText
			}
			const err = NextResponse.json({ statusText: message, code: res.status }, { status: res.ok ? 404 : res.status });
			applyBackendSetCookies(res, err);
			return err;
		}
		const safeLevel = level.replace(/[^A-Za-z0-9_.-]/g, "_");
		const out = new NextResponse(res.body, {
			status: 200,
			headers: {
				"Content-Type": "application/geo+json",
				"Content-Disposition": `attachment; filename="${safeLevel}-v${String(version)}.geojson"`,
				"Cache-Control": "no-store",
			},
		});
		applyBackendSetCookies(res, out);
		return out;
	} catch (e) {
		return NextResponse.json(
			{ statusText: e instanceof Error ? e.message : "Internal Server Error", code: 500 },
			{ status: 500 },
		);
	}
}
