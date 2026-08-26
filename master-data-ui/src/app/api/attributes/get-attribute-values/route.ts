import { NextRequest } from "next/server";
import { proxyToBackend } from "@/app/api/_lib/backend-proxy";

export async function POST(request: NextRequest) {
	return proxyToBackend({
		req: request,
		targetEndpoint: "/attributes/get_attribute_values",
		buildPayload: (body) => ({
			pagination_request: {
				current_page: body.page_number ?? body.current_page ?? 1,
				page_size: body.page_size ?? 1000,
				sort_by: body.sort_by ?? "",
				filter_by: body.filter_by ?? "",
				search_text: body.search_text ?? "",
			},
			request_payload: {
				attribute_id: body.attribute_id,
			},
		}),
		transformResponse: (responseBody) => ({
			attributeValues: responseBody?.response_payload?.attribute_values ?? [],
			total: responseBody?.response_payload?.total ?? responseBody?.pagination_response?.number_of_items ?? 0,
			pagination: responseBody?.pagination_response,
		}),
	});
}
