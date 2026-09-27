import { NextRequest } from "next/server";
import { proxyToBackend } from "@/app/api/_lib/backend-proxy";

export async function POST(request: NextRequest) {
	return proxyToBackend({
		req: request,
		targetEndpoint: "/attributes/get_all_attributes",
		buildPayload: (body) => ({
			pagination_request: {
				current_page: body.current_page ?? 1,
				page_size: body.page_size ?? 20,
				sort_by: body.sort_by ?? "",
				filter_by: body.filter_by ?? "",
				search_text: body.search_text ?? "",
			},
			request_payload: {},
		}),
		transformResponse: (responseBody) => ({
			attributes: responseBody?.response_payload?.attributes ?? [],
			pagination: responseBody?.pagination_response,
		}),
	});
}
