import { NextRequest } from "next/server";
import { proxyToBackend } from "@/app/api/_lib/backend-proxy";

export async function POST(request: NextRequest) {
	return proxyToBackend({
		req: request,
		targetEndpoint: "/attributes/add_attribute",
		buildPayload: (body) => ({
			pagination_request: {
				current_page: body.current_page ?? 1,
				page_size: body.page_size ?? 20,
				sort_by: body.sort_by ?? "",
				filter_by: body.filter_by ?? "",
				search_text: body.search_text ?? "",
			},
			request_payload: {
				attribute_code: body.attribute_code,
				attribute_display: body.attribute_display || body.attribute_code,
				is_hierarchical: body.is_hierarchical ?? false,
			},
		}),
		transformResponse: (responseBody) => responseBody?.response_payload,
	});
}
