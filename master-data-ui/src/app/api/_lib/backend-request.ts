import { randomUUID } from "crypto";
import type { BackendRequest, RequestBody } from "./backend-types";
import { getServerEnv } from "./env-config";

export function createBackendRequest(payload: RequestBody, origin: string): BackendRequest {
    return {
        request_header: {
            sender_app_mnemonic: getServerEnv().applicationMnemonic,
            sender_app_url: origin,
            request_id: randomUUID(),
            request_timestamp: new Date().toISOString(),
        },
        request_body: payload,
    };
}
