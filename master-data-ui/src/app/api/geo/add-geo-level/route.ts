import { NextRequest } from "next/server";
import { proxyToBackend } from "@/app/api/_lib/backend-proxy";

export async function POST(request: NextRequest) {
	return proxyToBackend({
		req: request,
		targetEndpoint: "/geo/add_geo_level",
		buildPayload: (body) => ({
			pagination_request: {
				current_page: body.current_page ?? 1,
				page_size: body.page_size ?? 20,
				sort_by: body.sort_by ?? "",
				filter_by: body.filter_by ?? "",
				search_text: body.search_text ?? "",
			},
			request_payload: {
				level_mnemonic: body.level_mnemonic,
				display_name: body.display_name || body.level_mnemonic,
				parent_level_id: body.parent_level_id ?? null,
			},
		}),
		transformResponse: (responseBody) => responseBody?.response_payload,
	});
}
