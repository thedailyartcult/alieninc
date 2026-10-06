const allowedOrigins = [
  "https://thedailyartcult.com",
  "https://www.thedailyartcult.com",
  "https://thedailyartcult.lol",
  "https://www.thedailyartcult.lol",
  "https://art.alieninc.tech",
  "https://art.alieninc.tech/accounts",
  "https://art.alieninc.tech/support",
  "https://art.alieninc.tech/policy",
  "http://localhost:9999",
  "http://127.0.0.1:5500",
  "http://localhost:3000"
];

function getAllowedOrigin(origin) {
  if (allowedOrigins.includes(origin)) return origin;
  // Browsers send bare Origin (scheme+host, no path) — accept any path under an allowed base
  for (const base of allowedOrigins) {
    if (origin === base || origin.startsWith(base + "/")) return origin;
  }
  if (origin && origin.endsWith(".art.alieninc.tech")) return origin;
  return "https://art.alieninc.tech";
}

function extractYouTubeVideoId(input) {
  const value = String(input || "").trim();
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtube\.com\/shorts\/|youtu\.be\/)([A-Za-z0-9_-]{11})/,
    /^[A-Za-z0-9_-]{11}$/
  ];

  for (const pattern of patterns) {
    const match = value.match(pattern);
    if (match) return match[1] || match[0];
  }

  return "";
}

function decodeHtmlEntities(value) {
  return String(value || "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

async function fetchYouTubeMeta(videoId) {
  try {
    const res = await fetch(`https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`);
    if (!res.ok) return {};
    const data = await res.json();
    return { title: data.title || "", author: data.author_name || "" };
  } catch (_) {
    return {};
  }
}

function transcriptFromJson3(transcriptJson) {
  return ((transcriptJson.events || [])
    .flatMap((event) => event.segs || [])
    .map((seg) => seg.utf8 || "")
    .join(" ")
    .replace(/\s+/g, " ")
    .trim()).slice(0, 24000);
}

async function fetchCaptionText(baseUrl) {
  const url = decodeHtmlEntities(baseUrl).replace(/\\u0026/g, "&");
  const sep = url.includes("?") ? "&" : "?";
  const res = await fetch(`${url}${sep}fmt=json3`);
  if (!res.ok) return { ok: false, status: res.status, transcript: "" };
  const transcript = transcriptFromJson3(await res.json());
  return { ok: true, status: 200, transcript };
}

async function fetchViaInnertube(videoId) {
  // ANDROID client returns captionTracks + videoDetails without scraping HTML.
  // Works from datacenter/edge IPs where watch-page HTML is bot-walled.
  const res = await fetch("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      videoId,
      context: { client: { clientName: "ANDROID", clientVersion: "20.10.38" } }
    })
  });
  if (!res.ok) return { status: `innertube_${res.status}` };
  const player = await res.json();
  const details = player.videoDetails || {};
  const tracks = player.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
  const preferred = tracks.find((t) => String(t.languageCode || "").startsWith("en")) || tracks[0];
  const meta = {
    title: details.title || "",
    author: details.author || "",
    description: String(details.shortDescription || "").slice(0, 2000)
  };
  if (!preferred?.baseUrl) return { status: tracks.length ? "no_caption_url" : "no_public_caption_tracks", ...meta };
  const cap = await fetchCaptionText(preferred.baseUrl);
  if (cap.ok && cap.transcript) return { status: "transcript_found", transcript: cap.transcript, ...meta };
  return { status: cap.ok ? "empty_transcript" : `caption_fetch_${cap.status}`, transcript: "", ...meta };
}

async function fetchViaWatchPage(videoId) {
  const pageRes = await fetch(`https://www.youtube.com/watch?v=${videoId}`, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"
    }
  });
  if (!pageRes.ok) return { status: `youtube_page_${pageRes.status}` };
  const page = await pageRes.text();
  const tracksMatch = page.match(/"captionTracks":(\[.*?\])\s*,\s*"audioTracks"/);
  if (!tracksMatch) return { status: "no_public_caption_tracks" };
  const captionTracks = JSON.parse(decodeHtmlEntities(tracksMatch[1]));
  const preferredTrack = captionTracks.find((track) => String(track.languageCode || "").startsWith("en")) || captionTracks[0];
  if (!preferredTrack?.baseUrl) return { status: "no_caption_url" };
  const cap = await fetchCaptionText(preferredTrack.baseUrl);
  if (cap.ok) return { status: cap.transcript ? "transcript_found" : "empty_transcript", transcript: cap.transcript };
  return { status: `caption_fetch_${cap.status}` };
}

async function fetchYouTubeTranscript(sourceInput) {
  const videoId = extractYouTubeVideoId(sourceInput);
  if (!videoId) {
    return { videoId: "", transcript: "", status: "not_youtube" };
  }

  try {
    // 1) Innertube first (edge-safe), 2) watch-page scrape fallback.
    // Always attach oEmbed title/author so Gemini can speak to the real
    // video even when captions are unavailable.
    const [innertube, meta] = await Promise.all([
      fetchViaInnertube(videoId).catch((e) => ({ status: "transcript_lookup_failed", _err: e?.message })),
      fetchYouTubeMeta(videoId)
    ]);
    const merged = {
      videoId,
      transcript: innertube.transcript || "",
      status: innertube.status || "transcript_lookup_failed",
      title: innertube.title || meta.title || "",
      author: innertube.author || meta.author || "",
      description: innertube.description || ""
    };
    if (merged.status === "transcript_found" && merged.transcript) return merged;

    const fallback = await fetchViaWatchPage(videoId).catch((e) => ({ status: "transcript_lookup_failed", _err: e?.message }));
    if (fallback.transcript) {
      return { ...merged, transcript: fallback.transcript, status: "transcript_found" };
    }
    // Keep the most informative failure status, but never drop the title.
    if (fallback.status && merged.status !== "transcript_found") {
      const rank = (s) => s === "no_public_caption_tracks" ? 0 : 1;
      if (rank(String(fallback.status)) < rank(String(merged.status))) merged.status = fallback.status;
    }
    return merged;
  } catch (err) {
    console.error("YouTube transcript lookup failed:", err.message);
    const meta = await fetchYouTubeMeta(videoId);
    return { videoId, transcript: "", status: "transcript_lookup_failed", title: meta.title || "", author: meta.author || "", description: "" };
  }
}

Deno.serve(async (req) => {
  const origin = req.headers.get("Origin") || "";
  
  // If the request comes from an allowed origin, echo it back. Otherwise, default to your main production domain.
  const corsHeaders = {
    'Access-Control-Allow-Origin': getAllowedOrigin(origin),
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Vary': 'Origin',
  };

  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  // Parse inputs safely with defaults to prevent runtime destructuring errors
  let q1 = "";
  let q2 = "";
  let q3 = "";
  let first_name = "Patron";
  let honorary = "Master";
  let worldview = "";
  let philosopher = "";
  let content_source = "";
  let source_input = "";

  try {
    const body = await req.json().catch(() => ({}));
    q1 = body.q1 || "";
    q2 = body.q2 || "";
    q3 = body.q3 || "";
    first_name = body.first_name || "Patron";
    honorary = body.honorary || "Master";
    worldview = body.worldview || "";
    philosopher = body.philosopher || "";
    content_source = body.content_source || "";
    source_input = body.source_input || "";
  } catch (err) {
    console.error("JSON parsing warning:", err.message);
  }

  const isMarkdownArchive = q1 === "Markdown archive provided" || q2 === "Archive mode";
  const isSourceMaterial = content_source === "source_material" || q1 === "Source material provided" || q2 === "Source mode";
  const targetName = first_name.trim() || "Patron";
  const targetHonorary = honorary.trim() || "Master";

  try {
    const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY")
    
    if (!GEMINI_API_KEY) {
      throw new Error("GEMINI_API_KEY is not defined in Supabase environment variables.")
    }

    const API_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`

    let prompt = "";

    if (isMarkdownArchive) {
      prompt = `
        You are the curator of "The Daily Art Cult," a high-end, deeply sensitive, and articulate philosophical companion. 
        The user has trusted you with their structured permanent context profile (.md file) to customize future responses.
        
        The user's first name is: "${targetName}"
        Their desired honorary title is: "${targetHonorary}"
        
        Here is the profile details they uploaded:
        "${q3}"

        Your task is to analyze this file carefully and write a warm, custom greeting that integrates this context into their reading experience.

        Follow these strict instructions:
        1. SELECT THE TRUEST EMOTIONAL "TERRITORY":
           - Choose exactly one word from this list: [loss, becoming, longing, belonging, endurance, creation, love, faith, wonder].
        2. WRITE A "bridge_line":
           - A very short, poetic, custom sentence (max 10 words) that bridges their specific operating system with our quiet library. Never use standard templates. Do not write any markdown (no asterisks, bolding, or hashtags).
        3. WRITE AN "expanded_text" THAT INCORPORATES USER NAME, TITLE, AND DEEP EMPATHY:
           - Write exactly 2-4 warm, deeply conversational sentences.
           - CRITICAL GREETING RULE (NON-NEGOTIABLE): You MUST begin the "expanded_text" string by directly addressing the user using their honorary title and first name. You must start exactly with a variation of: "Welcome, ${targetHonorary} ${targetName}, to the quiet sanctuary of The Daily Art Cult." or "Good day, ${targetHonorary} ${targetName}. I have carefully integrated your personal ledger into the library archive." 
           - Tone: Act as a gentle, unhurried companion. Speak directly to their unique intellectual self-concept and psychological architecture. Dissolve any underlying performance anxiety, intellectual guilt, or creative stagnation. Give them permission to simply be a seeker here.
           - Directly but gracefully reference specific elements from their profile (e.g., if their profile lists Nietzsche, Autodidacticism, or a specific active project, reference it with immense dignity).
           - ADAPT your speaking style to their stated preferences in "Section 7 (Communication Preferences)" of their profile. If they prefer directness, nuance, or a specific register, use it here.
           - Do not write any markdown formatting (no asterisks, hash marks, or HTML tags) so the Text-to-Speech system parses the string cleanly.

        Return ONLY a JSON object in this exact format:
        {
          "territory": "chosen_word",
          "bridge_line": "...",
          "expanded_text": "..."
        }
      `;
    } else if (isSourceMaterial) {
      const sourceInput = source_input || q3;
      const transcriptLookup = await fetchYouTubeTranscript(sourceInput);
      const isYouTube = transcriptLookup.status !== "not_youtube";
      const videoMeta = isYouTube && (transcriptLookup.title || transcriptLookup.author)
        ? `Known video metadata — title: "${transcriptLookup.title || "unknown"}", channel: "${transcriptLookup.author || "unknown"}"${transcriptLookup.description ? `, description excerpt: "${transcriptLookup.description.slice(0, 1200)}"` : ""}.`
        : "";
      const transcriptContext = transcriptLookup.transcript
        ? `Verified public YouTube transcript for video id ${transcriptLookup.videoId}${transcriptLookup.title ? ` ("${transcriptLookup.title}" by ${transcriptLookup.author || "unknown channel"})` : ""}:\n"${transcriptLookup.transcript}"`
        : isYouTube
          ? `The submitted source is a YouTube video (${sourceInput}, video id ${transcriptLookup.videoId}). No public transcript could be verified (lookup status: ${transcriptLookup.status}). ${videoMeta} Do not pretend to have read the captions and do not use the phrase "verified captions" or "awaits verified captions". Instead, speak directly to the video's actual title/channel/subject using your own knowledge of its themes, name the title in your preface, and say you are beginning from the source they gave.`
          : `The submitted source appears to be a book title or named text:\n"${sourceInput}"`;

      prompt = `
        You are the curator of "The Daily Art Cult," a high-end, deeply sensitive, and articulate philosophical companion.
        The user submitted source material they want to understand. The source may be a YouTube link or a book title.

        The user's first name is: "${targetName}"
        Their desired honorary title is: "${targetHonorary}"

        Source input:
        "${sourceInput}"

        Source verification context:
        ${transcriptContext}

        Your task is to understand the source material and prepare a short personal audiobook introduction that directs the user toward the worldview publisher most suited to the material's underlying philosophical pressure.

        Follow these strict instructions:
        1. SELECT THE TRUEST EMOTIONAL OR INTELLECTUAL "TERRITORY":
           - Choose exactly one from: [loss, becoming, longing, belonging, endurance, creation, love, faith, wonder].
           - For YouTube transcripts, base this on the verified transcript when present.
           - For book titles, base this on the known themes of the book if you know them; if not, infer cautiously from the title and avoid pretending certainty.
        2. WRITE A "bridge_line":
           - A very short, poetic, custom sentence (max 10 words) that bridges the submitted source into the recommended worldview. Do not write markdown.
        3. WRITE AN "expanded_text":
           - Write exactly 2-4 warm, deeply conversational sentences.
           - CRITICAL GREETING RULE: Begin by directly addressing the user with their title and first name.
            - If a YouTube transcript was verified, mention that you found the public transcript and are reading the source through its central concern.
            - If no transcript was verified, name the video's title/channel explicitly and speak to its known themes; never output generic "archive awaits verified captions" language.
           - If it is a book, speak to the book's central question and why it belongs near the recommended worldview.
           - Do not summarize mechanically. Compose it as a personal audio preface that prepares them for the suggested worldview publisher.
           - Do not write any markdown formatting, hash marks, or HTML tags.

        Return ONLY a JSON object in this exact format:
        {
          "territory": "chosen_word",
          "bridge_line": "...",
          "expanded_text": "..."
        }
      `;
    } else {
      prompt = `
        You are the curator of "The Daily Art Cult," a high-end, deeply sensitive, and articulate philosophical companion. 
        A user has trusted you with an exclusive, highly vulnerable, and raw part of their life. 
        
        The user's first name is: "${targetName}"
        Their desired honorary title is: "${targetHonorary}"
        
        Here is what they shared:
        1. What they are carrying: "${q1}"
        2. Ending or Beginning: "${q2}"
        3. What they need from this: "${q3}"

        Your task is to honor this trust by writing a response that is completely unique, highly conversational, and deeply comforting. 

        Follow these strict instructions:
        1. SELECT THE TRUEST EMOTIONAL "TERRITORY":
           - Choose exactly one from: [loss, becoming, longing, belonging, endurance, creation, love, faith, wonder].
           - Do not treat grief as a flat default. If they talk about a mother passing but seek connection or peace, choose the territory that matches the truest spiritual tone of their input (e.g., "love", "longing", "endurance", "belonging", or "wonder").
        2. WRITE A "bridge_line":
           - A very short, poetic, custom sentence (max 10 words) that directly speaks to the specific gravity of their input. Never repeat standard templates. Do not write any markdown (no asterisks or bolding).
        3. WRITE AN "expanded_text" THAT ALIEVIATES HUMAN HARDSHIP AND EMPHASIZES GENTLE KINDNESS:
           - Write exactly 2-4 warm, deeply comforting sentences.
           - CRITICAL GREETING RULE (NON-NEGOTIABLE): You MUST begin the "expanded_text" string by directly addressing the user using their honorary title and first name. You must start exactly with a variation of: "Good morning ${targetHonorary} ${targetName}, welcome back to The Daily Art Cult." or "Welcome, ${targetHonorary} ${targetName}, I have prepared our reflection on what you carry."
           - CORE SPIRIT: Speak to them with profound, unhurried, human-to-human empathy. Do not treat their struggles, pain, or grief as problems to solve, tasks to finish, or flaws to correct. Wrap their vulnerability in absolute solidarity and quiet warmth.
           - GENTLE SOLIDARITY: If they are carrying guilt, regret, or heavy responsibility, gently remind them that carrying a heavy heart is a courageous act of love, and that they are permitted to rest. Let them feel completely seen, accepted, and safe in this space.
           - Gently and respectfully reference specific elements or concepts they shared (e.g., if they mention their mother, reference that memory with immense dignity).
           - NEVER use generic, pre-written AI transitions, templates, or cliches (such as "I hear the depth of what you shared", "your growth is unfolding", "even in the quietest moments"). Speak like an old friend writing a direct, custom letter from a quiet library.
           - Do not write any markdown formatting (no asterisks, hash marks, or HTML tags) so the Text-to-Speech system parses the string cleanly.

        Return ONLY a JSON object in this exact format:
        {
          "territory": "chosen_word",
          "bridge_line": "...",
          "expanded_text": "..."
        }
      `;
    }

    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          responseMimeType: "application/json"
        },
        safetySettings: [
          { category: "HARM_CATEGORY_HARASSMENT", threshold: "BLOCK_NONE" },
          { category: "HARM_CATEGORY_HATE_SPEECH", threshold: "BLOCK_NONE" },
          { category: "HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold: "BLOCK_NONE" },
          { category: "HARM_CATEGORY_DANGEROUS_CONTENT", threshold: "BLOCK_NONE" }
        ]
      })
    })

    if (!response.ok) {
      const errText = await response.text()
      throw new Error(`Gemini API returned status ${response.status}: ${errText}`)
    }

    const data = await response.json()
    
    if (!data.candidates || data.candidates.length === 0) {
      throw new Error("No response candidates returned.")
    }

    const resultText = data.candidates[0].content.parts[0].text
    const parsedResult = JSON.parse(resultText.trim())

    return new Response(JSON.stringify(parsedResult), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" }
    })

  } catch (error) {
    console.error("Gemini Error:", error.message)
    
    // Fallback response explicitly respects user-provided target variables with warmth
    const targetName = first_name || "Patron";
    const targetHonorary = honorary || "Master";
    
    return new Response(JSON.stringify({
      territory: "becoming",
      bridge_line: "In the quiet space of what remains.",
      expanded_text: `Welcome back, ${targetHonorary} ${targetName}. When words fall short, please know that your thoughts are met here with absolute dignity, quiet attention, and an unhurried peace.`
    }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" }
    })
  }
})
