import { NextRequest } from "next/server";
import { proxyToBackend } from "@/app/api/_lib/backend-proxy";

export async function POST(request: NextRequest) {
	return proxyToBackend({
		req: request,
		targetEndpoint: "/attributes/add_attribute_value",
		buildPayload: (body) => ({
			pagination_request: {
				current_page: body.current_page ?? 1,
				page_size: body.page_size ?? 20,
				sort_by: body.sort_by ?? "",
				filter_by: body.filter_by ?? "",
				search_text: body.search_text ?? "",
			},
			request_payload: {
				attribute_id: body.attribute_id,
				value_code: body.value_code,
				value_display: body.value_display || body.value_code,
				parent_value_id: body.parent_value_id ?? null,
				sort_order: body.sort_order ?? 0,
			},
		}),
		transformResponse: (responseBody) => responseBody?.response_payload,
	});
}
