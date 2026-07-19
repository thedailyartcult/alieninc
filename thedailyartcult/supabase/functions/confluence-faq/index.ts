// supabase/functions/confluence-faq/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const ALLOWED_ORIGINS = [
  "https://thedailyartcult.lol",
  "https://support.thedailyartcult.lol"
];

serve(async (req: Request) => {
  const origin = req.headers.get("Origin");
  const allowedOrigin = origin && ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];

  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": allowedOrigin,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
      },
    });
  }

  // 1. Read secrets and trim accidental whitespaces
  let BASE_URL     = (Deno.env.get("CONFLUENCE_BASE_URL") || "").trim();
  const EMAIL      = (Deno.env.get("CONFLUENCE_EMAIL") || "").trim();
  const API_TOKEN  = (Deno.env.get("CONFLUENCE_API_TOKEN") || "").trim();
  const SPACE_KEY  = (Deno.env.get("CONFLUENCE_SPACE_KEY") || "").trim();

  if (!BASE_URL || !EMAIL || !API_TOKEN || !SPACE_KEY) {
    return json({ error: "Missing environment variables." }, 500, allowedOrigin);
  }

  // 2. Safe URL extraction: extracts the correct base domain regardless of what was pasted
  try {
    const parsed = new URL(BASE_URL);
    BASE_URL = `${parsed.origin}/wiki`;
  } catch {
    BASE_URL = BASE_URL.replace(/\/+$/, "");
    if (!BASE_URL.endsWith("/wiki")) {
      BASE_URL = `${BASE_URL}/wiki`;
    }
  }

  const credentials = btoa(`${EMAIL}:${API_TOKEN}`);
  const cql = `space = "${SPACE_KEY}" AND label = "faq" AND type = "page"`;
  const url = `${BASE_URL}/rest/api/content/search?cql=${encodeURIComponent(cql)}&expand=body.view,metadata.labels&limit=50`;

  // 3. Diagnostic Logging (Visible in your Supabase Dashboard "Logs" tab)
  console.log("--- DIAGNOSTIC SYSTEM LOGS ---");
  console.log(`Confluence Space Key: "${SPACE_KEY}"`);
  console.log(`Target Request URL:   "${url}"`);
  console.log(`Email (First 3 ch):   "${EMAIL.slice(0, 3)}..." (Total length: ${EMAIL.length})`);
  console.log(`Token (First 3 ch):   "${API_TOKEN.slice(0, 3)}..." (Total length: ${API_TOKEN.length})`);
  console.log("------------------------------");

  try {
    const res = await fetch(url, {
      headers: {
        Authorization: `Basic ${credentials}`,
        Accept: "application/json",
      },
    });

    if (!res.ok) {
      const text = await res.text();
      console.error(`Confluence rejected request with status ${res.status}: ${text}`);
      return json({ error: `Confluence API Error: ${text}` }, res.status, allowedOrigin);
    }

    const data = await res.json();
    console.log(`Successfully fetched ${data.results?.length || 0} pages.`);

    const faqs = (data.results ?? []).map((page: any) => ({
      id:    page.id,
      title: page.title,
      body:  page.body?.view?.value || "",
      url:   `${BASE_URL}${page._links?.webui || ""}`,
    }));

    return json({ faqs }, 200, allowedOrigin);
  } catch (err) {
    console.error(`Execution error: ${String(err)}`);
    return json({ error: String(err) }, 500, allowedOrigin);
  }
});

function json(data: unknown, status = 200, allowedOrigin = "https://thedailyartcult.lol") {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": allowedOrigin,
      "Cache-Control": "no-cache",
    },
  });
}
