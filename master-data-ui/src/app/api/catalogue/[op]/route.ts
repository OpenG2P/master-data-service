import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/app/api/_lib/backend-proxy";

/**
 * Proxy for the Master Data catalogue API (`POST /catalogue/<op>` on master-data-api).
 *
 * Browser body: `{ payload: {...}, pagination?: { current_page, page_size } }`.
 * Forwarded as the standard envelope `{request_header, request_body: {request_payload, pagination_request}}`.
 * Response to the browser: `{ payload: response_payload, pagination: pagination_response }`;
 * backend errors come back as `{ statusText, code }` with a non-2xx status (see backend-proxy).
 *
 * Only the operations listed here are forwarded. Authorisation is enforced by the backend.
 */
const CATALOGUE_OPS = new Set([
	// lists
	"get_lists",
	"get_list",
	"get_list_values",
	"get_list_value",
	"get_list_versions",
	"get_list_diff",
	"create_list",
	"update_list",
	"create_list_draft",
	"update_list_draft",
	"upsert_draft_values",
	"retire_draft_values",
	"discard_draft",
	"submit_draft",
	"approve_draft",
	"reject_draft",
	// geography
	"get_geo_versions",
	"get_geo_levels",
	"get_geo_units",
	"get_geo_unit",
	"get_geo_changes",
	"get_geo_crosswalk",
	"get_geo_boundary",
	"create_geo_draft",
	"update_geo_draft",
	"upsert_draft_levels",
	"upsert_draft_units",
	"retire_draft_units",
	"record_geo_change",
	"delete_geo_change",
	"upload_draft_boundary",
	"submit_geo_draft",
	"approve_geo_draft",
	"reject_geo_draft",
	"discard_geo_draft",
	"get_geo_settings",
	"update_geo_settings",
	// releases
	"get_releases",
	"get_release",
	"create_release",
	"set_release_members",
	"publish_release",
	"delete_release",
	// feed and configuration
	"get_changes",
	"get_catalogue_config",
]);

export async function POST(
	request: NextRequest,
	{ params }: { params: Promise<{ op: string }> },
) {
	const { op } = await params;
	if (!CATALOGUE_OPS.has(op)) {
		return NextResponse.json(
			{ statusText: `Unknown catalogue operation: ${op}`, code: "G2P-REQ-404" },
			{ status: 404 },
		);
	}

	return proxyToBackend({
		req: request,
		targetEndpoint: `/catalogue/${op}`,
		buildPayload: (body) => {
			const payload = { ...(body?.payload ?? {}) };
			// Streaming GeoJSON goes through /api/catalogue-boundary, never through this JSON proxy.
			if (op === "get_geo_boundary") delete payload.stream;
			const pagination = body?.pagination;
			return {
				pagination_request: pagination
					? {
							current_page: pagination.current_page ?? 1,
							page_size: pagination.page_size ?? 100,
							sort_by: "",
							filter_by: "",
							search_text: "",
						}
					: undefined,
				request_payload: payload,
			};
		},
		transformResponse: (responseBody) => ({
			payload: responseBody?.response_payload ?? null,
			pagination: responseBody?.pagination_response ?? null,
		}),
	});
}
