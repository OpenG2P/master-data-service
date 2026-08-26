import { NextRequest } from "next/server";
import { proxyToBackend } from "@/app/api/_lib/backend-proxy";

export async function POST(request: NextRequest) {
	return proxyToBackend({
		req: request,
		targetEndpoint: "/geo/update_geo_level_value",
		buildPayload: (body) => ({
			pagination_request: {
				current_page: body.current_page ?? 1,
				page_size: body.page_size ?? 20,
				sort_by: body.sort_by ?? "",
				filter_by: body.filter_by ?? "",
				search_text: body.search_text ?? "",
			},
			request_payload: {
				level_value_id: body.level_value_id,
				level_value_mnemonic: body.level_value_mnemonic,
				parent_level_value_id: body.parent_level_value_id,
			},
		}),
		transformResponse: (responseBody) => responseBody?.response_payload,
	});
}
