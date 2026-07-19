const allowedOrigins = [
  "https://thedailyartcult.com",
  "https://www.thedailyartcult.com",
  "https://thedailyartcult.lol",
  "https://www.thedailyartcult.lol",
  "https://accounts.thedailyartcult.lol",
  "https://support.thedailyartcult.lol",
  "https://privacy.thedailyartcult.lol",
  "http://localhost:9999",
  "http://127.0.0.1:5500",
  "http://localhost:3000"
];

function getAllowedOrigin(origin) {
  return allowedOrigins.includes(origin) ? origin : "https://thedailyartcult.lol";
}

Deno.serve(async (req) => {
  const origin = req.headers.get("Origin") || "";
  const corsHeaders = {
    "Access-Control-Allow-Origin": getAllowedOrigin(origin),
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };

  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { text } = await req.json().catch(() => ({}));

    if (!text || typeof text !== "string" || text.trim().length === 0) {
      throw new Error("Missing or empty 'text' field");
    }

    const key = Deno.env.get("AZURE_SPEECH_KEY");
    const region = Deno.env.get("AZURE_SPEECH_REGION") || "eastus";

    if (!key) {
      throw new Error("AZURE_SPEECH_KEY is not configured");
    }

    const cleanedText = text
      .replace(/[*#_![\]-]/g, "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&apos;")
      .trim();

    const truncatedText = cleanedText.length > 2800
      ? `${cleanedText.substring(0, 2800)}...`
      : cleanedText;

    const ssml = `
      <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
        <voice name="en-US-BrianNeural">
          <prosody rate="-8%" pitch="-5%" volume="medium">
            ${truncatedText}
          </prosody>
        </voice>
      </speak>`;

    const response = await fetch(`https://${region}.tts.speech.microsoft.com/cognitiveservices/v1`, {
      method: "POST",
      headers: {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
        "User-Agent": "DailyArtCult-TTS"
      },
      body: ssml,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Azure TTS Error:", response.status, errorText);
      throw new Error(`Azure TTS failed: ${response.status}`);
    }

    const arrayBuffer = await response.arrayBuffer();

    return new Response(arrayBuffer, {
      status: 200,
      headers: {
        ...corsHeaders,
        "Content-Type": "audio/mpeg"
      }
    });
  } catch (error) {
    console.error("TTS Error:", error.message);

    return new Response(JSON.stringify({
      error: error.message,
      fallback: "TTS service temporarily unavailable. Please try again."
    }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" }
    });
  }
});
