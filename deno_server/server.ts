/**
 * Deno HTTP server to authenticate a Telegram user via Firebase Custom Auth.
 * Optimized for performance: Pre-computes crypto keys and reuses objects.
 */

import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import * as djwt from "https://deno.land/x/djwt@v3.0.2/mod.ts";

// --- Configuration ---
const TELEGRAM_BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN");
const FIREBASE_SERVICE_ACCOUNT_EMAIL = Deno.env.get("FIREBASE_SERVICE_ACCOUNT_EMAIL");
const FIREBASE_SERVICE_ACCOUNT_PRIVATE_KEY_RAW = Deno.env.get("FIREBASE_SERVICE_ACCOUNT_PRIVATE_KEY");
const FIREBASE_SERVICE_ACCOUNT_PRIVATE_KEY = FIREBASE_SERVICE_ACCOUNT_PRIVATE_KEY_RAW?.replace(/\\n/g, '\n');
const FIREBASE_PROJECT_ID = Deno.env.get("FIREBASE_PROJECT_ID");
const PORT = parseInt(Deno.env.get("PORT") || "8000", 10);

const GOOGLE_OAUTH_CLIENT_ID = Deno.env.get("GOOGLE_OAUTH_CLIENT_ID");
const GOOGLE_OAUTH_CLIENT_SECRET = Deno.env.get("GOOGLE_OAUTH_CLIENT_SECRET");

const FIREBASE_REST_API_URL = `https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit`;

// --- Global Cache ---
let CACHED_TELEGRAM_KEY: CryptoKey | null = null;
let CACHED_FIREBASE_KEY: CryptoKey | null = null;

const CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
};

// --- Helper: Validate Env & Initialize Keys ---
async function initializeServer() {
    if (!TELEGRAM_BOT_TOKEN) throw new Error("Missing: TELEGRAM_BOT_TOKEN");
    if (!FIREBASE_SERVICE_ACCOUNT_EMAIL) throw new Error("Missing: FIREBASE_SERVICE_ACCOUNT_EMAIL");
    if (!FIREBASE_SERVICE_ACCOUNT_PRIVATE_KEY) throw new Error("Missing: FIREBASE_SERVICE_ACCOUNT_PRIVATE_KEY");
    if (!FIREBASE_PROJECT_ID) throw new Error("Missing: FIREBASE_PROJECT_ID");
    if (!GOOGLE_OAUTH_CLIENT_ID) throw new Error("Missing: GOOGLE_OAUTH_CLIENT_ID");
    if (!GOOGLE_OAUTH_CLIENT_SECRET) throw new Error("Missing: GOOGLE_OAUTH_CLIENT_SECRET");

    console.log("Environment variables validated.");

    const encoder = new TextEncoder();

    // 1. Pre-compute Telegram Validation Key
    // Logic: Key = HMAC-SHA256(WebAppData, BotToken)
    try {
        const secretKeyMaterial = await crypto.subtle.importKey(
            "raw",
            encoder.encode("WebAppData"),
            { name: "HMAC", hash: "SHA-256" },
            false,
            ["sign"]
        );
        const secretKeyBytes = await crypto.subtle.sign(
            "HMAC",
            secretKeyMaterial,
            encoder.encode(TELEGRAM_BOT_TOKEN)
        );
        CACHED_TELEGRAM_KEY = await crypto.subtle.importKey(
            "raw",
            secretKeyBytes,
            { name: "HMAC", hash: "SHA-256" },
            false,
            ["sign"]
        );
        console.log("Telegram crypto key cached.");
    } catch (e) {
        throw new Error(`Failed to generate Telegram key: ${e.message}`);
    }

    // 2. Pre-parse Firebase Private Key
    try {
        const pem = FIREBASE_SERVICE_ACCOUNT_PRIVATE_KEY;
        const base64 = pem.replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\n/g, '');
        const binaryString = atob(base64);
        const len = binaryString.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        CACHED_FIREBASE_KEY = await crypto.subtle.importKey(
            "pkcs8",
            bytes.buffer,
            { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
            true,
            ["sign"]
        );
        console.log("Firebase private key cached.");
    } catch (e) {
        throw new Error(`Failed to parse Firebase key: ${e.message}`);
    }
}

// --- Helper: Hex String ---
function bufferToHex(buffer: ArrayBuffer): string {
    return Array.from(new Uint8Array(buffer))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
}

// --- Validation Logic ---
async function isTelegramDataValid(initDataString: string): Promise<{ isValid: boolean; data?: URLSearchParams; error?: string }> {
    if (!initDataString) return { isValid: false, error: "Missing initData." };
    if (!CACHED_TELEGRAM_KEY) return { isValid: false, error: "Server error: Keys not initialized." };

    try {
        const urlParams = new URLSearchParams(initDataString);
        const hash = urlParams.get("hash");
        if (!hash) return { isValid: false, error: "Hash missing." };

        const dataCheckArr: string[] = [];
        const sortedKeys = Array.from(urlParams.keys()).sort();
        for (const key of sortedKeys) {
            if (key !== "hash") dataCheckArr.push(`${key}=${urlParams.get(key)}`);
        }
        const dataCheckString = dataCheckArr.join("\n");

        const computedHashBuffer = await crypto.subtle.sign(
            "HMAC",
            CACHED_TELEGRAM_KEY,
            new TextEncoder().encode(dataCheckString)
        );

        const computedHash = bufferToHex(computedHashBuffer);

        if (computedHash === hash) {
            return { isValid: true, data: urlParams };
        } else {
            return { isValid: false, error: "Hash mismatch." };
        }
    } catch (error) {
        return { isValid: false, error: `Validation error: ${error.message}` };
    }
}

// --- Token Generation ---
async function createFirebaseCustomToken(uid: string): Promise<{ token?: string; error?: string }> {
    if (!CACHED_FIREBASE_KEY) return { error: "Server error: Firebase key not initialized." };

    const now = Math.floor(Date.now() / 1000);
    const expiry = now + 3600;

    try {
        const assertionToken = await djwt.create(
            { alg: "RS256", typ: "JWT" },
            {
                iss: FIREBASE_SERVICE_ACCOUNT_EMAIL,
                sub: FIREBASE_SERVICE_ACCOUNT_EMAIL,
                aud: FIREBASE_REST_API_URL,
                iat: now,
                exp: expiry,
                uid: uid,
            },
            CACHED_FIREBASE_KEY
        );
        return { token: assertionToken };
    } catch (error) {
        console.error("Token creation error:", error);
        return { error: `Token gen failed: ${error.message}` };
    }
}

// --- Request Handler ---
async function handler(req: Request): Promise<Response> {
    const url = new URL(req.url);

    // CORS Preflight
    if (req.method === "OPTIONS") {
        return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (req.method !== "POST" || url.pathname !== "/authenticate") {
        return new Response(JSON.stringify({ error: "Not Found" }), {
            status: 404, headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
        });
    }

    try {
        const body = await req.json();
        const initDataString = body.initData;
        const googleAuth = body.googleAuth;

        if (!initDataString || typeof initDataString !== 'string') {
            throw new Error("Invalid initData");
        }

        // 1. Validate Telegram Data
        const validation = await isTelegramDataValid(initDataString);
        if (!validation.isValid || !validation.data) {
            return new Response(JSON.stringify({ error: validation.error }), {
                status: 401, headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
            });
        }

        const userJson = validation.data.get("user");
        const userData = JSON.parse(userJson || "{}");
        if (!userData.id) throw new Error("No user ID in data");

        const telegramUserId = String(userData.id);

        // 2. Handle Google OAuth (if provided)
        let googleTokenPayload: any = null;
        if (googleAuth?.code) {
            try {
                const params = new URLSearchParams({
                    code: googleAuth.code,
                    client_id: GOOGLE_OAUTH_CLIENT_ID!,
                    client_secret: GOOGLE_OAUTH_CLIENT_SECRET!,
                    redirect_uri: googleAuth.redirect_uri,
                    grant_type: "authorization_code",
                });

                const tokenResp = await fetch("https://oauth2.googleapis.com/token", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: params.toString(),
                });

                if (tokenResp.ok) {
                    googleTokenPayload = await tokenResp.json();

                    // Get Email
                    if (googleTokenPayload.access_token) {
                        const userResp = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
                            headers: { "Authorization": `Bearer ${googleTokenPayload.access_token}` }
                        });
                        if (userResp.ok) {
                            const userInfo = await userResp.json();
                            googleTokenPayload.email = userInfo.email;
                            googleTokenPayload.email_verified = userInfo.verified_email;
                        }
                    }
                } else {
                    console.warn("Google Auth failed", await tokenResp.text());
                }
            } catch (e) {
                console.warn("Google Auth error", e);
            }
        }

        // 3. Generate Custom Token
        const tokenResult = await createFirebaseCustomToken(telegramUserId);
        if (tokenResult.error) throw new Error(tokenResult.error);

        return new Response(JSON.stringify({ customToken: tokenResult.token, google: googleTokenPayload }), {
            status: 200, headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
        });

    } catch (e: any) {
        console.error("Handler error:", e);
        return new Response(JSON.stringify({ error: e.message }), {
            status: 400, headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
        });
    }
}

// --- Server Entry ---
try {
    await initializeServer();
    console.log(`Server running on http://localhost:${PORT}/authenticate`);
    serve(handler, { port: PORT });
} catch (error: any) {
    console.error("Startup failed:", error.message);
    Deno.exit(1);
}
