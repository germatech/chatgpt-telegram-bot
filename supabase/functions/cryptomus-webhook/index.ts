// Follow this setup guide to integrate the Deno language server with your editor:
// https://deno.land/manual/getting_started/setup_your_environment
// This enables autocomplete, go to definition, etc.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

import {
  type ConnInfo,
} from 'https://deno.land/std@0.125.0/http/server.ts';
import { createHash } from "node:crypto";


function createSignatureError(message: string): SignatureError {
    const error = new Error(message) as SignatureError;
    error.name = 'SignatureError';
    return error;
}

function generate_signature(data: Record<string, any>, api_key: string): string | never {
    try {
        const dataStr = JSON.stringify(data);
        const encodedStr = Buffer.from(dataStr, 'utf-8').toString('base64');
        const sign = createHash('md5').update(`${encodedStr}${api_key}`).digest('hex');
        return sign;
    } catch (error: any) {
        throw createSignatureError(`Error generating signature: ${error.message}`);
    }
}

function extract_user_id(orderString: string): string | null {
    const regex = /-(\d+)-/;
    const match = orderString.match(regex);
    return match ? match[1] : null;
}


Deno.serve(async (req: Request) => {
    console.log("Received request");
    const authHeader = req.headers.get("Authorization")!;
    console.log("auth header " + authHeader);
    if (req.method !== "POST") {
        return new Response("Method Not Allowed", { status: 405 })
    }
//     console.log("remote address " + req.remoteAddr)
//     if (req.remoteAddr !== CRYPTOMUS_IP) {
//         logger.error("Error IP is unknown");
//         jsonResponse(req, { "error": "Unauthorized IP" }, 401);
//         return false;
//     }

    // Ensure the request is JSON formatted
//     if (!req.json()) {
//         logger.error("is not json");
//         jsonResponse(req, { "error": "Invalid request format" }, 400);
//         return false;
//     }

    try {
        const json = await req.json();
        console.log("this is the json " + json)
        const {
            type,
            uuid,
            order_id,
            amount,
            payment_amount,
            payment_amount_usd,
            merchant_amount,
            commission,
            is_final,
            status,
            from,
            wallet_address_uuid,
            network,
            currency,
            payer_currency,
            additional_data,
            convert,
            txid,
            sign,
            } = json;
            console.log(type);
        } catch (error) {
        return new Response(JSON.stringify({ status: 'error', message: error.message}), {
          headers: { 'Content-Type': 'application/json' },
          status: 500
        });
      }

});

/* To invoke locally:

  1. Run `supabase start` (see: https://supabase.com/docs/reference/cli/supabase-start)
  2. Make an HTTP request:

  curl -i --location --request POST 'http://127.0.0.1:54321/functions/v1/cryptomus-webhook' \
    --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU' \
    --header 'Content-Type: application/json' \
    --data '{  "type": "payment",
    "uuid": "62f88b36-a9d5-4fa6-aa26-e040c3dbf26d",
    "order_id": "97a75bf8eda5cca41ba9d2e104840fcd",
    "amount": "3.00000000",
    "payment_amount": "3.00000000",
    "payment_amount_usd": "0.23",
    "merchant_amount": "2.94000000",
    "commission": "0.06000000",
    "is_final": true,
    "status": "paid",
    "from": "THgEWubVc8tPKXLJ4VZ5zbiiAK7AgqSeGH",
    "wallet_address_uuid": null,
    "network": "tron",
    "currency": "TRX",
    "payer_currency": "TRX",
    "additional_data": null,
    "convert": {
        "to_currency": "USDT",
        "commission": null,
        "rate": "0.07700000",
        "amount": "0.22638000"
        },
    "txid": "6f0d9c8374db57cac0d806251473de754f361c83a03cd805f74aa9da3193486b",
    "sign": "a76c0d77f3e8e1a419b138af04ab600a"
    }'

*/
