import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const allowedOrigins = [
  "https://thedailyartcult.com",
  "https://www.thedailyartcult.com",
  "https://accounts.thedailyartcult.lol",
  "http://localhost:9999",      
  "http://127.0.0.1:5500",      
  "http://localhost:3000"       
];

Deno.serve(async (req) => {
  const origin = req.headers.get("Origin") || "";
  
  const corsHeaders = {
    'Access-Control-Allow-Origin': allowedOrigins.includes(origin) ? origin : 'https://accounts.thedailyartcult.lol',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
  };

  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? ''
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    const geminiApiKey = Deno.env.get('GEMINI_API_KEY') ?? ''
    const azureSpeechKey = Deno.env.get('AZURE_SPEECH_KEY') ?? ''
    const azureRegion = Deno.env.get('AZURE_SPEECH_REGION') || 'eastus'

    if (!supabaseUrl || !supabaseServiceKey) {
      throw new Error('System configuration error: Missing Supabase variables.')
    }

    const supabase = createClient(supabaseUrl, supabaseServiceKey)
    const { issue_id, test_user_id } = await req.json().catch(() => ({}))

    // 1. Locate Target Issue
    let issue;
    if (issue_id) {
      const { data, error } = await supabase
        .from('publisher_issues')
        .select('*')
        .eq('id', issue_id)
        .single()
      if (error || !data) throw new Error(`Publisher issue not found: ${error?.message}`)
      issue = data
    } else {
      const { data, error } = await supabase
        .from('publisher_issues')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(1)
        .single()
      if (error || !data) throw new Error(`No active publisher issues exist: ${error?.message}`)
      issue = data
    }

    // 2. Query target subscribers with their profile AND memory attributes
    let subscribers = []
    if (test_user_id) {
      const { data, error } = await supabase
        .from('user_contexts')
        .select('user_id, markdown_text, completed_topics, last_reflection_summary')
        .eq('user_id', test_user_id)
        .single()
      if (error || !data) throw new Error(`Test user lacks context: ${error?.message}`)
      subscribers = [data]
    } else {
      const { data, error } = await supabase
        .from('user_contexts')
        .select('user_id, markdown_text, completed_topics, last_reflection_summary')
      if (error) throw new Error(`Failed to load profiles: ${error.message}`)
      subscribers = data ?? []
    }

    const outputLog = []

    // 3. Synthesis and Memory Pipeline loop
    for (const sub of subscribers) {
      try {
        const userId = sub.user_id
        const userContext = sub.markdown_text || ''
        const pastTopics = sub.completed_topics || []
        const pastSummary = sub.last_reflection_summary || 'No prior study logged yet.'

        // Instruct Gemini to write the script and record the session's memory
        const prompt = `
You are the curator of "The Daily Art Cult," a high-end, deeply sensitive, and articulate philosophical companion. 
The client has trusted you with their context profile to personalize their next spoken-word audio compilation.

Your task is to analyze their context profile and our latest publisher issue, and write an unhurried, comfortable spoken-word reflection (approx. 200-300 words).

---
PUBLISHER ISSUE TOPIC:
"${issue.base_prompt}"

---
CLIENT PROFILE CONTEXT:
"${userContext}"

---
PREVIOUS SESSION MEMORY (TEMPORAL CONTINUITY):
- The client previously integrated these concepts into their arsenal: [${pastTopics.join(', ') || 'None yet'}]
- Summary of their last session: "${pastSummary}"

STRICT INSTRUCTIONS:
1. GENTLE TRANSITION: If they have a previous study summary, you MUST gracefully acknowledge it in the script's first two sentences (e.g., "Returning to our reflections on Stoic composure last week..." or "Now that you have anchored Nietzsche into your arsenal...").
2. NO MARKDOWN: Write warm, natural spoken-word sentences. Do not use any markdown formatting (no asterisks, hash marks, or HTML tags) so the voice synth reads it cleanly.
3. OUTPUT FORMAT: You must return ONLY a JSON object containing the script, a concise 1-sentence summary of this new session, and a list of 2-3 specific topics/concepts covered in this script.

Return ONLY a JSON object in this exact format:
{
  "script": "spoken script text goes here...",
  "session_summary": "A 1-sentence summary of what this session discussed.",
  "new_tags": ["TopicA", "TopicB"]
}
`

        if (!geminiApiKey) throw new Error('System key missing: GEMINI_API_KEY')
        const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${geminiApiKey}`
        const geminiRes = await fetch(geminiUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
            generationConfig: {
              temperature: 0.65,
              maxOutputTokens: 1000,
              responseMimeType: "application/json"
            }
          })
        })

        if (!geminiRes.ok) {
          const errText = await geminiRes.text()
          throw new Error(`Gemini Error: ${geminiRes.status} - ${errText}`)
        }

        const geminiData = await geminiRes.json()
        const rawJsonString = geminiData.candidates?.[0]?.content?.parts?.[0]?.text
        if (!rawJsonString) throw new Error('Gemini returned empty content.')

        // Parse script & memory
        const parsedPayload = JSON.parse(rawJsonString.trim())
        const synthesizedScript = parsedPayload.script
        const newSummary = parsedPayload.session_summary
        const generatedTags = parsedPayload.new_tags || []

        // Clean script text for TTS engine
        const cleanedText = synthesizedScript
          .replace(/[*#_\-\[\]!]/g, "") 
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&apos;")
          .trim();

        const truncatedText = cleanedText.length > 2800 
          ? cleanedText.substring(0, 2800) + "..." 
          : cleanedText;

        const ssml = `
          <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
            <voice name="en-US-BrianNeural">
              <prosody rate="-8%" pitch="-5%" volume="medium">
                ${truncatedText}
              </prosody>
            </voice>
          </speak>`;

        if (!azureSpeechKey) throw new Error("AZURE_SPEECH_KEY is not configured")
        const azureUrl = `https://${azureRegion}.tts.speech.microsoft.com/cognitiveservices/v1`
        const ttsRes = await fetch(azureUrl, {
          method: "POST",
          headers: {
            "Ocp-Apim-Subscription-Key": azureSpeechKey,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            "User-Agent": "DailyArtCult-TTS-Compiler"
          },
          body: ssml,
        });

        if (!ttsRes.ok) {
          const errText = await ttsRes.text()
          throw new Error(`Azure TTS Error: ${ttsRes.status} - ${errText}`)
        }

        const arrayBuffer = await ttsRes.arrayBuffer()
        const audioBuffer = new Uint8Array(arrayBuffer)

        // Upload generated audio directly to private folder under user's ID
        const storagePath = `private/${userId}/${issue.id}.mp3`
        const { error: uploadError } = await supabase.storage
          .from('audio-releases')
          .upload(storagePath, audioBuffer, {
            contentType: 'audio/mpeg',
            upsert: true
          })

        if (uploadError) throw new Error(`Private storage failed: ${uploadError.message}`)

        // Update database ledger for the audio release
        const { error: insertError } = await supabase
          .from('audio_releases')
          .insert({
            user_id: userId,
            issue_id: issue.id,
            title: issue.title,
            description: `A personalized synthesis compiled on your philosophical context.`,
            storage_path: storagePath
          })

        if (insertError) throw new Error(`Ledger entry failed: ${insertError.message}`)

        // UPDATE THE USER'S CONTEXT FILE (Save new summary and append new tags)
        const updatedTags = Array.from(new Set([...pastTopics, ...generatedTags]))
        const { error: contextUpdateError } = await supabase
          .from('user_contexts')
          .update({
            completed_topics: updatedTags,
            last_reflection_summary: newSummary,
            updated_at: new Date().toISOString()
          })
          .eq('user_id', userId)

        if (contextUpdateError) throw new Error(`Context state update failed: ${contextUpdateError.message}`)

        outputLog.push({ user_id: userId, status: 'completed', tags_added: generatedTags })
      } catch (childErr) {
        console.error(`Bespoke pipeline failed for user ${sub.user_id}:`, childErr)
        outputLog.push({ user_id: sub.user_id, status: 'failed', error: childErr.message })
      }
    }

    return new Response(JSON.stringify({ status: 'success', summary: outputLog }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    })

  } catch (globalErr) {
    console.error("Global compilation failed:", globalErr)
    return new Response(JSON.stringify({ status: 'error', error: globalErr.message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    })
  }
})
