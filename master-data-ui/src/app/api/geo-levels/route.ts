import { NextRequest } from "next/server";
import { proxyToBackend } from "@/app/api/_lib/backend-proxy";

export async function POST(req: NextRequest) {
    return proxyToBackend({
        req,
        targetEndpoint: "/geo/get_all_g2p_geo_levels",
        buildPayload: (body) => ({
            pagination_request: {
                current_page: (body.current_page as number) ?? 1,
                page_size: (body.page_size as number) ?? 10,
                sort_by: (body.sort_by as string) ?? "",
                filter_by: (body.filter_by as string) ?? "",
                search_text: (body.search_text as string) ?? "",
            },
            request_payload: {},
        }),
    });
}
