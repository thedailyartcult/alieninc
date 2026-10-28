    // --- SUPABASE CONFIGURATION ---
    const SUPABASE_URL = "https://frwjaixxlgthkgjtafhz.supabase.co"; 
    const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZyd2phaXh4bGd0aGtnanRhZmh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDUzNDQsImV4cCI6MjA5NDYyMTM0NH0.j2DKz__QMml4WplMYNmsQpTUw0qu-kZG7Md3qBEEdEc"; 
    
    // Named "supabaseClient" to avoid library name collisions
    const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    // --- DOM REFERENCES ---
    const authGate = document.getElementById("auth-gate");
    const dashboard = document.getElementById("dashboard");
    const loginForm = document.getElementById("login-form");
    const emailInput = document.getElementById("email");
    const passwordInput = document.getElementById("password");
    const magicLinkBtn = document.getElementById("magic-link-btn");
    const authFeedback = document.getElementById("auth-feedback");
    const AUTH_REDIRECT_URL = "https://art.alieninc.tech/accounts/";
    const logoutBtn = document.getElementById("logout-btn");
    
    const patronGreeting = document.getElementById("patron-greeting");
    const profileForm = document.getElementById("profile-form");
    const profileMdText = document.getElementById("profile-md-text");
    const profileStatus = document.getElementById("profile-status");
    
    const audioPlayerHud = document.getElementById("audio-player-hud");
    const mainAudioPlayer = document.getElementById("main-audio-player");
    const hudTrackTitle = document.getElementById("hud-track-title");
    const releasesList = document.getElementById("releases-list");
    const speechPlayerControls = document.getElementById("speech-player-controls");
    const speechPauseBtn = document.getElementById("speech-pause-btn");
    const speechRestartBtn = document.getElementById("speech-restart-btn");
    const speechStopBtn = document.getElementById("speech-stop-btn");
    const speechPlayerStatus = document.getElementById("speech-player-status");

    // NEW DOM REFERENCES FOR DRAG & DROP / COPY
    const dropZone = document.getElementById("md-drop-zone");
    const dropZoneIdle = document.getElementById("drop-zone-idle");
    const mdFileInput = document.getElementById("md-file-input");
    const revealPasteBtn = document.getElementById("reveal-paste-btn");
    const copyPromptBtn = document.getElementById("copy-profile-prompt-btn");
    
    // NATAL FOUNDATION (DATE OF BIRTH) REFERENCES
    const birthMonthSelect = document.getElementById("birth-month");
    const birthDaySelect = document.getElementById("birth-day");

    function populateBirthDays(selectedMonth, currentDayValue) {
      if (!birthDaySelect) return;
      const month = parseInt(selectedMonth, 10);
      const maxDays = [2].includes(month) ? 29 : [4, 6, 9, 11].includes(month) ? 30 : 31;
      
      const currentDay = currentDayValue ? parseInt(currentDayValue, 10) : parseInt(birthDaySelect.value, 10);
      birthDaySelect.innerHTML = '<option value="">Day</option>';
      for (let d = 1; d <= maxDays; d++) {
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = d;
        if (currentDay === d) opt.selected = true;
        birthDaySelect.appendChild(opt);
      }
    }

    if (birthMonthSelect) {
      birthMonthSelect.addEventListener('change', () => {
        populateBirthDays(birthMonthSelect.value);
      });
    }
    
    // --- NEW REFERENCES FOR ACTIVE LENSES ---
    const availableWorldviews = [
      "Becoming", "Existentialism", "Stoicism", "Absurdism", "The Leap", "Mysticism", "Eastern Wisdom", "Politics", "Witness",
      "Guideposts", "Angels on Earth", "Mysterious Ways", "Mornings with Jesus", "Strength & Grace"
    ];
    let activeWorldviews = [];
    let sourceMaterials = [];
    let profileContext = '';
    let accountHandoff = readAccountHandoff();
    let speechSessionId = 0;
    let speechState = {
      text: '',
      title: '',
      chunks: [],
      index: 0,
      isPlaying: false,
      isPaused: false
    };

    function escapeHtml(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function decodeAccountHandoff(value) {
      try {
        return JSON.parse(decodeURIComponent(escape(atob(value))));
      } catch (e) {
        console.error("Account handoff decode failed:", e);
        return null;
      }
    }

    function readAccountHandoff() {
      const params = new URLSearchParams(window.location.search);
      const handoff = params.get('handoff');
      if (!handoff) return null;

      const decoded = decodeAccountHandoff(handoff);
      params.delete('handoff');
      const cleanUrl = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ''}${window.location.hash}`;
      window.history.replaceState({}, document.title, cleanUrl);
      return decoded;
    }

    function extractYouTubeVideoId(value) {
      const text = String(value || '').trim();
      const patterns = [
        /(?:youtube\.com\/watch\?v=|youtube\.com\/shorts\/|youtu\.be\/)([A-Za-z0-9_-]{11})/,
        /^[A-Za-z0-9_-]{11}$/
      ];

      for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) return match[1] || match[0];
      }

      return '';
    }

    function getSourceVisual(item) {
      const videoId = item.youtube_video_id || extractYouTubeVideoId(item.source_input);
      if (item.thumbnail_url || videoId) {
        return {
          kind: 'youtube',
          label: 'YouTube Transcript',
          thumbnail: item.thumbnail_url || `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`
        };
      }

      return {
        kind: 'book',
        label: 'Book Study',
        thumbnail: ''
      };
    }

    // --- PROMPT TEXT CONSTANT ---
    const PROFILE_PROMPT_TEXT = `# Prompt: Generate My Personal Learning & Context Profile> **How to use this:** Paste everything below the horizontal rule into a new Claude conversation. Claude will synthesize everything it knows about you from past sessions into a \`.md\` file you can attach to future conversations as context.

---

Claude, I want you to generate a \`.md\` file that functions as my **permanent personal context profile** — a living document I'll attach to future conversations so you can calibrate how you engage with me from the very first message.

Pull from everything you know about me across all our past conversations. Structure the output as follows:

---

## 1. Identity & Intellectual Self-Concept
Who I understand myself to be. My core intellectual identity, the thinkers I self-identify with, my relationship to autodidactic learning vs. institutional frameworks, and any recurring self-images or archetypes that surface in how I think and speak.

## 2. Philosophical Architecture
The thinkers and texts that form my actual operating system — not what I've casually mentioned, but what shapes *how I think*. Include:
- Primary canon (deeply internalized)
- Secondary influences (engaged but not foundational)
- Tensions or productive contradictions between my influences
- How I use philosophy: instrumentally, aesthetically, ethically, or otherwise

## 3. Psychological Profile (as observed across conversations)
Patterns in how I engage, learn, and respond. Include:
- How I process new information (do I go broad first or drill immediately?)
- My relationship to structure vs. intuition
- Where I show high curiosity vs. resistance
- How I respond to challenge, disagreement, or complexity
- Any recurring cognitive or emotional patterns

## 4. Astrological / Archetypal Lens *(if inferable)*
Any astrological, Jungian, or archetypal framing that maps to how I operate — either things I've stated directly or patterns consistent with known frameworks.

## 5. Learning Style & Pedagogy Preferences
How I learn fastest. Include:
- Do I prefer Socratic dialogue, direct transmission, or exploratory synthesis?
- Do I respond better to analogies, first principles, or narrative?
- My preferred density of information (concise vs. rich)
- How I respond to examples, counterexamples, and edge cases
- My tolerance for ambiguity vs. need for resolution

## 6. Active Projects & Working Context
The professional and creative work currently underway that shapes what I need from our conversations. Be specific — project names, platforms, goals, current blockers if known.

## 7. Communication Preferences
How I like Claude to speak to me. Tone, register, format preferences, things I find annoying or useful, whether I prefer directness or nuance-first delivery.

## 8. Blind Spots & Growth Edges *(observed, not prescribed)*
Patterns where I seem to avoid, rush past, or undervalue something that might serve me. Note these diplomatically — this section is for my benefit, not critique.

## 9. One-Line Summary
A single sentence that captures me as a learner and thinker — precise enough that another version of Claude reading it cold would immediately know how to engage me.

---

**Output format:** A clean \`.md\` file, ready to be saved and attached to future conversations. Use headers, subheaders, and bullet points where clarity demands it — but write in a register that sounds like *me*, not a clinical report. Treat it as a document I'd actually want to read.`;

// 1. This function grabs any temporary selections from the landing page and saves them permanently
    async function syncPendingWorldviews(userId) {
      const pending = localStorage.getItem('pending_worldviews');
      const handoffList = Array.isArray(accountHandoff?.selected_worldviews) ? accountHandoff.selected_worldviews : [];
      if (pending || handoffList.length) {
        try {
          const pendingList = pending ? JSON.parse(pending) : [];
          const combinedList = Array.from(new Set([...pendingList, ...handoffList]));
          if (Array.isArray(combinedList) && combinedList.length > 0) {
            const { data } = await supabaseClient
              .from('user_contexts')
              .select('selected_worldviews')
              .eq('user_id', userId)
              .single();

            const currentList = data?.selected_worldviews || [];
            const merged = Array.from(new Set([...currentList, ...combinedList]));

            await supabaseClient
              .from('user_contexts')
              .upsert({
                user_id: userId,
                selected_worldviews: merged,
                updated_at: new Date().toISOString()
              }, { onConflict: 'user_id' });
          }
        } catch (e) {
          console.error("Local sync error:", e);
        } finally {
          localStorage.removeItem('pending_worldviews'); // Clear the temp memory
        }
      }
    }

    async function syncPendingSourceMaterials(userId) {
      const pending = localStorage.getItem('pending_source_materials');
      const handoffList = Array.isArray(accountHandoff?.source_materials) ? accountHandoff.source_materials : [];
      if (!pending && handoffList.length === 0) return [];

      let pendingList = [];
      try {
        pendingList = pending ? JSON.parse(pending) : [];
      } catch (e) {
        console.error("Source material parse error:", e);
      }

      pendingList = Array.isArray(pendingList) ? pendingList : [];
      const combinedList = [...pendingList, ...handoffList];
      if (combinedList.length === 0) return [];

      try {
        const { data } = await supabaseClient
          .from('user_contexts')
          .select('*')
          .eq('user_id', userId)
          .single();

        const currentList = Array.isArray(data?.source_materials) ? data.source_materials : [];
        const mergedMap = new Map();

        [...currentList, ...combinedList].forEach((item) => {
          if (!item) return;
          const key = item.id || item.source_input || `${item.source_title}-${item.created_at}`;
          mergedMap.set(key, item);
        });

        const merged = Array.from(mergedMap.values());

        const { error } = await supabaseClient
          .from('user_contexts')
          .upsert({
            user_id: userId,
            source_materials: merged,
            updated_at: new Date().toISOString()
          }, { onConflict: 'user_id' });

        if (error) throw error;

        localStorage.removeItem('pending_source_materials');
        return merged;
      } catch (e) {
        console.error("Source material sync error:", e);
        return combinedList;
      }
    }

    // 2. This function builds the visual clickable buttons (toggles) dynamically
    function renderActiveLenses(userId) {
      const container = document.getElementById('active-lenses-grid');
      if (!container) return;

      container.innerHTML = availableWorldviews.map(wv => {
        const isSelected = activeWorldviews.includes(wv);
        return `
          <button type="button" 
            class="w-full text-left p-2.5 rounded-xl border text-[10px] font-mono uppercase tracking-wider transition duration-200 ${
              isSelected 
                ? 'bg-alienGold/15 border-alienGold text-alienGold shadow-sm font-semibold' 
                : 'bg-[#0b0f14] border-white/10 text-linen hover:border-white/25 hover:text-white'
            }"
            onclick="toggleLens('${wv}', '${userId}')">
            <span class="mr-1.5 ${isSelected ? 'text-alienGold' : 'text-white/30'}">${isSelected ? '●' : '○'}</span> ${wv}
          </button>
        `;
      }).join('');
      updateCalibrationSummaryPill();
    }

    // 3. This function runs when a user clicks any toggle button
    window.toggleLens = async function(title, userId) {
      const idx = activeWorldviews.indexOf(title);
      if (idx > -1) {
        activeWorldviews.splice(idx, 1); // Remove if already selected
      } else {
        activeWorldviews.push(title); // Add if not selected
      }
      
      renderActiveLenses(userId);
      updateCalibrationSummaryPill();
      profileStatus.textContent = "Updating lenses...";

      const { error } = await supabaseClient
        .from('user_contexts')
        .upsert({
          user_id: userId,
          selected_worldviews: activeWorldviews,
          updated_at: new Date().toISOString()
        }, { onConflict: 'user_id' });

      if (error) {
        profileStatus.textContent = "Error saving lenses";
        console.error(error);
      } else {
        profileStatus.textContent = "Saved to vault";
      }
    };  

    // --- STATE ROUTER ---
    supabaseClient.auth.onAuthStateChange((event, session) => {
      if (session) {
        authGate.classList.add("hidden");
        dashboard.classList.remove("hidden");
        loadMemberDashboard(session.user);
      } else {
        stopBrowserSpeech({ hideControls: true });
        dashboard.classList.add("hidden");
        authGate.classList.remove("hidden");
      }
    });

    // --- HANDLERS ---

    // 1. Email + Password Sign In
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = emailInput.value.trim();
      const password = passwordInput ? passwordInput.value : "";
      if (!email || !password) {
        authFeedback.textContent = "Email and password are required.";
        return;
      }
      authFeedback.textContent = "Verifying credentials...";

      const { error } = await supabaseClient.auth.signInWithPassword({
        email: email,
        password: password
      });

      if (error) {
        authFeedback.textContent = error.message || "Sign in failed. Check your credentials.";
      } else {
        authFeedback.textContent = "";
        loginForm.reset();
      }
    });

    // 2. Email Magic-Link Sign In
    if (magicLinkBtn) {
      magicLinkBtn.addEventListener("click", async () => {
        const email = emailInput.value.trim();
        if (!email) {
          authFeedback.textContent = "Enter your email address first.";
          emailInput.focus();
          return;
        }
        magicLinkBtn.disabled = true;
        authFeedback.textContent = "Sending sign-in link...";

        const { error } = await supabaseClient.auth.signInWithOtp({
          email: email,
          options: {
            emailRedirectTo: AUTH_REDIRECT_URL,
            shouldCreateUser: false
          }
        });

        magicLinkBtn.disabled = false;
        authFeedback.textContent = error
          ? `Error: ${error.message}`
          : "Check your inbox. The link returns you here and signs you in.";
      });
    }

    // 3. Logout Click
    logoutBtn.addEventListener("click", async () => {
      await supabaseClient.auth.signOut();
    });

    // --- MEMBER DASHBOARD LOGIC ---
    async function loadMemberDashboard(user) {
      const displayName = (user.email ? user.email.split('@')[0] : 'Employee');
      patronGreeting.textContent = `Welcome, ${displayName}`;

      // Fetch User's .md Context
      await fetchUserContext(user.id);

      // Fetch Pre-Generated Personalized Releases
      fetchUserReleases(user.id);
    }

// Replace your old fetchUserContext function with this one:
    async function fetchUserContext(userId) {
      profileStatus.textContent = "Loading profile...";
      
      // Perform pending local sync if applicable
      await syncPendingWorldviews(userId);
      const pendingSources = await syncPendingSourceMaterials(userId);

      const { data, error } = await supabaseClient
        .from('user_contexts')
        .select('*')
        .eq('user_id', userId)
        .single();

      if (error && error.code !== 'PGRST116') { 
        console.error("Context fetch failed:", error);
        profileStatus.textContent = "Error reading profile.";
      } else if (data) {
        // 1. Context text area
        profileMdText.value = data.markdown_text || '';
        profileContext = data.markdown_text || '';
        activeWorldviews = data.selected_worldviews || [];
        sourceMaterials = Array.isArray(data.source_materials) ? data.source_materials : pendingSources;
        profileStatus.textContent = "Saved to vault";
        
        // 2. Render Last Reflection Summary
        const lastSummaryEl = document.getElementById("arsenal-last-summary");
        if (lastSummaryEl) {
          lastSummaryEl.textContent = data.last_reflection_summary || "No prior studies cataloged.";
        }

        // 3. Render Arsenal acquired tags
        const tagsContainer = document.getElementById("arsenal-tags-container");
        if (tagsContainer) {
          const completed = data.completed_topics || [];
          if (completed.length === 0) {
            tagsContainer.innerHTML = `<span class="text-[9px] text-linen/30 italic">Complete your first study session to populate your study history.</span>`;
          } else {
            tagsContainer.innerHTML = completed.map(tag => `
              <span class="inline-flex items-center bg-antique/10 border border-antique/20 text-antique px-2.5 py-1 rounded-md text-[9px] font-mono uppercase tracking-wider">
                🛡️ ${tag}
              </span>
            `).join('');
          }
        }

        // Auto-show editor layouts
        profileMdText.classList.remove("hidden");
        dropZoneIdle.classList.add("hidden");
        dropZone.classList.remove("border-dashed");
        dropZone.classList.add("border-antique/50", "bg-black/25");
      } else {
        profileStatus.textContent = "Profile empty";
        profileContext = profileMdText.value || '';
        activeWorldviews = [];
        sourceMaterials = pendingSources;
      }

      renderActiveLenses(userId);

      // 4. Populate Natal Foundation (Date of Birth) if saved
      let natalMonth = localStorage.getItem('tdac_natal_month') || '';
      let natalDay = localStorage.getItem('tdac_natal_day') || '';

      try {
        const authRes = await supabaseClient.auth.getUser();
        const authUser = authRes?.data?.user;
        if (authUser?.user_metadata?.birth_month) {
          natalMonth = String(authUser.user_metadata.birth_month);
          natalDay = String(authUser.user_metadata.birth_day || '');
        }
      } catch (_) {}

      // Also parse metadata header if present in markdown_text
      if (data && data.markdown_text) {
        const natalMatch = data.markdown_text.match(/<!--\s*natal:\s*(\{.*?\})\s*-->/);
        if (natalMatch) {
          try {
            const parsed = JSON.parse(natalMatch[1]);
            if (parsed.month) natalMonth = String(parsed.month);
            if (parsed.day) natalDay = String(parsed.day);
          } catch (_) {}
        }
      }

      if (birthMonthSelect && natalMonth) {
        birthMonthSelect.value = natalMonth;
        populateBirthDays(natalMonth, natalDay);
      }

      updateCalibrationSummaryPill();
    }

    // B. Save Context File to DB
    profileForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      profileStatus.textContent = "Securing modifications...";
      
      const user = (await supabaseClient.auth.getUser()).data.user;
      if (!user) return;

      let updatedText = profileMdText.value;
      const selectedMonth = birthMonthSelect ? birthMonthSelect.value : '';
      const selectedDay = birthDaySelect ? birthDaySelect.value : '';

      if (selectedMonth && selectedDay) {
        localStorage.setItem('tdac_natal_month', selectedMonth);
        localStorage.setItem('tdac_natal_day', selectedDay);

        // Update auth user_metadata
        supabaseClient.auth.updateUser({
          data: { birth_month: selectedMonth, birth_day: selectedDay }
        }).catch(err => console.warn("User metadata update:", err));

        // Embed in markdown header so it stays permanently in user_contexts table
        const cleanText = updatedText.replace(/<!--\s*natal:\s*\{.*?\}\s*-->\n?/, '').trim();
        updatedText = `<!-- natal: {"month":${selectedMonth},"day":${selectedDay}} -->\n${cleanText}`;
        profileMdText.value = updatedText;
      }
      profileContext = updatedText;

      // Upsert profile text
      const { error } = await supabaseClient
        .from('user_contexts')
        .upsert({ 
          user_id: user.id, 
          markdown_text: updatedText, 
          updated_at: new Date().toISOString() 
        }, { onConflict: 'user_id' });

      if (error) {
        profileStatus.textContent = "Error saving";
        console.error(error);
      } else {
        profileStatus.textContent = "Saved to vault";
        updateCalibrationSummaryPill();
      }
    });

    // C. Fetch Releases list
    async function fetchUserReleases(userId) {
      releasesList.innerHTML = '<p class="text-xs text-linen/30 italic py-6 text-center">Loading your readings...</p>';

      const { data, error } = await supabaseClient
        .from('audio_releases')
        .select('id, title, storage_path, description, created_at')
        .eq('user_id', userId);
      
      if (error) {
        console.error("Failed to load releases:", error);
        releasesList.innerHTML = '<p class="text-xs text-linen/30 italic py-6 text-center">Error loading your readings.</p>';
        return;
      }

      if (!data || data.length === 0) {
        releasesList.innerHTML = '';
        renderSourceMaterialReleases();
        if (releasesList.children.length === 0) {
          releasesList.innerHTML = '<p class="text-xs text-linen/30 italic py-6 text-center">No readings yet. Submit a study request to generate your first one.</p>';
        }
        return;
      }

      releasesList.innerHTML = '';
      renderSourceMaterialReleases();
      data.forEach(item => {
        const row = document.createElement("div");
        row.className = "group overflow-hidden rounded-2xl border border-white/10 bg-[#121820]/75 p-6 text-left transition duration-300 hover:border-alienGold/35 hover:bg-[#161d26]/85 shadow-lg";
        
        // Clean and format date
        const formattedDate = new Date(item.created_at).toLocaleDateString(undefined, {
          year: 'numeric',
          month: 'long',
          day: 'numeric'
        });

        row.innerHTML = `
          <div class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <span class="text-[9px] font-mono uppercase tracking-[0.22em] text-alienGold font-bold">Audiobook Release</span>
              <span class="text-[9px] font-mono text-linen/40">${formattedDate}</span>
            </div>
            <h4 class="text-xl font-bold text-white group-hover:text-alienGold transition duration-200">${item.title}</h4>
            <p class="text-xs text-linen leading-relaxed">${item.description}</p>
            <button class="play-btn inline-flex items-center gap-2 rounded-xl bg-alienGold hover:bg-[#ffe033] px-5 py-2.5 text-xs font-mono font-bold uppercase tracking-wider text-ink transition shadow-md shadow-alienGold/10" data-path="${item.storage_path}" data-title="${item.title}">
              <span>▶</span> Play Audiobook
            </button>
          </div>
        `;

        // Handle Play Click (Fetch secure Signed URL from Supabase Private Storage Bucket)
        const playBtn = row.querySelector(".play-btn");
        playBtn.addEventListener("click", async () => {
          const storagePath = playBtn.dataset.path;
          const trackTitle = playBtn.dataset.title;

          playBtn.innerHTML = "<span>◌</span> Preparing audio...";

          const { data: signedData, error: signedError } = await supabaseClient
            .storage
            .from('audio-releases')
            .createSignedUrl(storagePath, 600);

          if (signedError) {
            console.error("Signed URL retrieval failed:", signedError);
            playBtn.innerHTML = "<span>▶</span> Playback Failed";
          } else if (signedData) {
            playBtn.innerHTML = "<span>▶</span> Play Audiobook";
            playAudio(signedData.signedUrl, trackTitle);
          }
        });

        releasesList.appendChild(row);
      });
    }

    function renderSourceMaterialReleases() {
      if (!Array.isArray(sourceMaterials) || sourceMaterials.length === 0) return;

      sourceMaterials
        .slice()
        .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
        .forEach(item => {
          const row = document.createElement("div");
          row.className = "source-release-card group grid overflow-hidden rounded-2xl text-left md:grid-cols-[minmax(190px,0.85fr)_minmax(0,1.4fr)]";

          const formattedDate = item.created_at
            ? new Date(item.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
            : 'Recently';
          const lenses = Array.isArray(item.selected_worldviews) && item.selected_worldviews.length
            ? item.selected_worldviews.join(', ')
            : item.worldview || 'Becoming';
          const hasAudioText = Boolean(item.expanded_text);
          const title = escapeHtml(item.source_title || 'Study Request');
          const description = escapeHtml(`Study request saved for ${lenses}. ${item.bridge_line || 'Your personalized study audio is held in your account.'}`);
          const sourceInput = escapeHtml(item.source_input || '');
          const visual = getSourceVisual(item);
          const visualLabel = escapeHtml(visual.label);
          const thumb = escapeHtml(visual.thumbnail);
          const territoryTag = escapeHtml(item.territory || item.worldview || 'becoming');
          const imageHtml = thumb
            ? `<img src="${thumb}" alt="${title} thumbnail" loading="lazy" onerror="this.remove(); this.closest('.source-release-thumb').classList.add('is-fallback');">`
            : `<div class="flex h-full min-h-[10rem] items-end p-5">
                <div>
                  <span class="block text-[9px] font-mono uppercase tracking-[0.24em] text-alienGold">Synthesis</span>
                  <span class="mt-1 block text-2xl font-bold text-white">Study<br>Vault</span>
                </div>
              </div>`;

          row.innerHTML = `
            <div class="source-release-thumb relative">
              ${imageHtml}
              <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 to-transparent p-4 flex items-center justify-between">
                <span class="inline-flex rounded-full border border-white/20 bg-black/60 px-2.5 py-0.5 text-[8px] font-mono uppercase tracking-wider text-white backdrop-blur">${visualLabel}</span>
                <span class="inline-flex rounded-full border border-alienGold/40 bg-black/70 px-2 py-0.5 text-[8px] font-mono uppercase tracking-wider text-alienGold backdrop-blur font-semibold">#${territoryTag}</span>
              </div>
            </div>
            <div class="source-release-content flex min-h-[14rem] flex-col justify-between gap-4 p-5 sm:p-6">
              <div class="space-y-3">
                <div class="flex items-center justify-between gap-3">
                  <span class="text-[9px] font-mono uppercase tracking-[0.2em] text-alienGold font-bold">Personalized Reading</span>
                  <div class="flex items-center gap-3">
                    <span class="text-[9px] font-mono text-linen/40">${formattedDate}</span>
                    <button type="button" class="delete-reading-btn inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-mono text-rose-400/60 hover:text-rose-400 hover:bg-rose-500/10 border border-transparent hover:border-rose-500/20 transition cursor-pointer" title="Remove reading from vault">
                      <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      <span>Remove</span>
                    </button>
                  </div>
                </div>
                <h4 class="text-xl sm:text-2xl font-bold leading-tight text-white transition duration-200 group-hover:text-alienGold">${title}</h4>
                <p class="text-xs text-linen leading-relaxed">${description}</p>
                <p class="rounded-lg border border-white/5 bg-black/35 px-3 py-1.5 text-[10px] font-mono text-white/40 truncate">${sourceInput}</p>
                ${hasAudioText ? `<details class="rounded-xl border border-white/10 bg-black/30 p-3"><summary class="text-[9px] font-mono uppercase tracking-wider text-alienBlue hover:text-white cursor-pointer font-semibold">View Spoken Transcript</summary><div class="mt-2 text-xs text-linen/80 leading-relaxed whitespace-pre-wrap max-h-[220px] overflow-y-auto pr-2">${escapeHtml(item.expanded_text)}</div></details>` : ''}
              </div>
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pt-2 border-t border-white/5">
                <span class="text-[9px] font-mono uppercase tracking-[0.18em] text-linen/50">${escapeHtml(lenses)}</span>
                <button class="source-play-btn inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-xs font-mono font-bold uppercase tracking-wider transition active:scale-[0.98] shadow-md shadow-alienGold/10" ${hasAudioText ? '' : 'disabled'}>
                  <span>${hasAudioText ? '▶' : '◌'}</span> ${hasAudioText ? 'Listen to Summary' : 'Queued'}
                </button>
              </div>
            </div>
          `;

          // Handle Remove Click
          const deleteBtn = row.querySelector(".delete-reading-btn");
          if (deleteBtn) {
            deleteBtn.addEventListener("click", async (e) => {
              e.stopPropagation();
              const itemKey = item.id || item.source_input || `${item.source_title}-${item.created_at}`;
              if (!confirm(`Remove "${item.source_title || 'this reading'}" from your study vault?`)) {
                return;
              }

              row.style.opacity = '0';
              row.style.transform = 'scale(0.97)';
              row.style.transition = 'all 0.25s ease';

              // Filter out of memory
              sourceMaterials = sourceMaterials.filter(sm => {
                const k = sm.id || sm.source_input || `${sm.source_title}-${sm.created_at}`;
                return k !== itemKey;
              });

              // Update local storage
              try {
                const existing = JSON.parse(localStorage.getItem('pending_source_materials') || '[]');
                const filtered = existing.filter(sm => {
                  const k = sm.id || sm.source_input || `${sm.source_title}-${sm.created_at}`;
                  return k !== itemKey;
                });
                localStorage.setItem('pending_source_materials', JSON.stringify(filtered));
              } catch (_) {}

              // Update Supabase
              try {
                const { data: { session } } = await supabaseClient.auth.getSession();
                if (session?.user?.id) {
                  await supabaseClient
                    .from('user_contexts')
                    .upsert({
                      user_id: session.user.id,
                      source_materials: sourceMaterials,
                      updated_at: new Date().toISOString()
                    }, { onConflict: 'user_id' });
                }
              } catch (err) {
                console.error("Database removal error:", err);
              }

              setTimeout(() => {
                row.remove();
                if (releasesList && releasesList.children.length === 0) {
                  releasesList.innerHTML = '<p class="text-xs text-linen/40 italic py-12 text-center font-mono">No readings in vault. Submit a study request above to generate one.</p>';
                }
              }, 250);
            });
          }

          const playBtn = row.querySelector(".source-play-btn");
          if (hasAudioText) {
            playBtn.addEventListener("click", async () => {
              const readingText = item.expanded_text.trim();
              const readingTitle = item.source_title || 'Study Request';
              playBtn.innerHTML = "<span>◌</span> Starting reading...";

              // Browser Speech Synthesis is free and starts immediately. Azure remains a
              // legacy fallback for browsers that do not expose the native speech API.
              if (startBrowserSpeech(readingText, readingTitle)) {
                playBtn.innerHTML = "<span>↻</span> Restart Reading";
                return;
              }

              try {
                const ttsRes = await fetch("https://frwjaixxlgthkgjtafhz.supabase.co/functions/v1/tts", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ text: readingText })
                });

                if (ttsRes.ok) {
                  const blob = await ttsRes.blob();
                  const audioUrl = URL.createObjectURL(blob);
                  playAudio(audioUrl, readingTitle, readingText);
                  playBtn.innerHTML = "<span>▶</span> Listen to Summary";
                  return;
                }
              } catch (error) {
                console.error("Source reading playback failed:", error);
              }

              // Keep the summary readable on browsers without a usable voice.
              playAudio('', readingTitle, readingText || 'No summary available.');
              playBtn.innerHTML = "<span>▶</span> Show Summary";
            });
          }

          releasesList.appendChild(row);
        });
    }

    // D. Playback helpers. Browser Speech Synthesis is used first so the
    // personalized Gemini text remains listenable while hosted TTS is offline.
    function supportsBrowserSpeech() {
      return typeof window !== 'undefined'
        && 'speechSynthesis' in window
        && typeof SpeechSynthesisUtterance !== 'undefined';
    }

    function clearAudioPlayer() {
      if (!mainAudioPlayer) return;
      mainAudioPlayer.pause();
      mainAudioPlayer.removeAttribute('src');
      mainAudioPlayer.load();
    }

    function showTranscript(transcript = '') {
      const transcriptPanel = document.getElementById('audio-transcript-panel');
      const transcriptContent = document.getElementById('audio-transcript-content');
      const toggleTranscript = document.getElementById('toggle-transcript');

      if (transcript && transcriptPanel && transcriptContent) {
        transcriptContent.textContent = transcript;
        transcriptPanel.classList.remove('hidden');
        if (toggleTranscript) {
          toggleTranscript.textContent = 'Hide';
          transcriptContent.classList.remove('hidden');
          toggleTranscript.onclick = () => {
            if (transcriptContent.classList.contains('hidden')) {
              transcriptContent.classList.remove('hidden');
              toggleTranscript.textContent = 'Hide';
            } else {
              transcriptContent.classList.add('hidden');
              toggleTranscript.textContent = 'Show';
            }
          };
        }
      } else if (transcriptPanel) {
        transcriptPanel.classList.add('hidden');
      }
    }

    function splitSpeechText(text, maxChars = 240) {
      const normalized = String(text || '')
        .replace(/[`*_#]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
      if (!normalized) return [];

      const sentences = normalized.match(/[^.!?]+(?:[.!?]+|$)/g) || [normalized];
      const chunks = [];
      let chunk = '';

      const pushLongSentence = (sentence) => {
        let longChunk = '';
        sentence.split(/\s+/).forEach((word) => {
          const candidate = `${longChunk} ${word}`.trim();
          if (candidate.length > maxChars && longChunk) {
            chunks.push(longChunk);
            longChunk = word;
          } else {
            longChunk = candidate;
          }
        });
        if (longChunk) chunks.push(longChunk);
      };

      sentences.forEach((sentence) => {
        const cleanSentence = sentence.trim();
        if (!cleanSentence) return;
        if (!chunk) {
          if (cleanSentence.length > maxChars) {
            pushLongSentence(cleanSentence);
          } else {
            chunk = cleanSentence;
          }
          return;
        }

        const candidate = `${chunk} ${cleanSentence}`.trim();
        if (candidate.length <= maxChars) {
          chunk = candidate;
          return;
        }

        chunks.push(chunk);
        chunk = '';
        if (cleanSentence.length > maxChars) {
          pushLongSentence(cleanSentence);
        } else {
          chunk = cleanSentence;
        }
      });

      if (chunk) chunks.push(chunk);
      return chunks;
    }

    function preferredSpeechVoice() {
      if (!supportsBrowserSpeech()) return null;
      const voices = window.speechSynthesis.getVoices();
      const englishVoices = voices.filter((voice) => /^en(?:-|_)/i.test(voice.lang));
      const preferred = englishVoices.find((voice) => /Samantha|Ava|Jenny|Aria|Google US English|Microsoft.*(Aria|Jenny|Guy|Davis)/i.test(voice.name));
      return preferred || englishVoices.find((voice) => /^en-US/i.test(voice.lang)) || englishVoices[0] || voices[0] || null;
    }

    function updateSpeechControls(status) {
      if (!speechPlayerControls) return;
      speechPlayerControls.classList.remove('hidden');
      if (speechPlayerStatus && status) speechPlayerStatus.textContent = status;
      if (speechPauseBtn) {
        speechPauseBtn.textContent = speechState.isPaused ? 'Resume' : 'Pause';
        speechPauseBtn.disabled = !speechState.isPlaying;
        speechPauseBtn.classList.toggle('opacity-40', !speechState.isPlaying);
      }
      if (speechRestartBtn) {
        speechRestartBtn.disabled = !speechState.text;
        speechRestartBtn.classList.toggle('opacity-40', !speechState.text);
      }
      if (speechStopBtn) {
        speechStopBtn.disabled = !speechState.isPlaying;
        speechStopBtn.classList.toggle('opacity-40', !speechState.isPlaying);
      }
    }

    function stopBrowserSpeech({ hideControls = false } = {}) {
      speechSessionId += 1;
      if (supportsBrowserSpeech()) window.speechSynthesis.cancel();
      speechState.isPlaying = false;
      speechState.isPaused = false;

      if (hideControls && speechPlayerControls) {
        speechPlayerControls.classList.add('hidden');
      } else {
        updateSpeechControls('Reading stopped');
      }
    }

    function startBrowserSpeech(text, title) {
      if (!supportsBrowserSpeech()) return false;

      const chunks = splitSpeechText(text);
      if (!chunks.length) return false;

      speechSessionId += 1;
      const sessionId = speechSessionId;
      window.speechSynthesis.cancel();
      window.speechSynthesis.resume();
      speechState = {
        text: String(text || '').trim(),
        title,
        chunks,
        index: 0,
        isPlaying: true,
        isPaused: false
      };

      clearAudioPlayer();
      mainAudioPlayer.classList.add('hidden');
      hudTrackTitle.textContent = title;
      audioPlayerHud.classList.remove('hidden');
      showTranscript(speechState.text);
      updateSpeechControls('Starting free browser voice...');

      const speakNext = () => {
        if (sessionId !== speechSessionId || !speechState.isPlaying) return;
        if (speechState.index >= speechState.chunks.length) {
          speechState.isPlaying = false;
          speechState.isPaused = false;
          updateSpeechControls('Reading complete');
          return;
        }

        const utterance = new SpeechSynthesisUtterance(speechState.chunks[speechState.index]);
        const voice = preferredSpeechVoice();
        if (voice) utterance.voice = voice;
        utterance.lang = voice?.lang || 'en-US';
        utterance.rate = 0.92;
        utterance.pitch = 0.96;

        utterance.onstart = () => {
          if (sessionId !== speechSessionId) return;
          speechState.isPlaying = true;
          speechState.isPaused = false;
          updateSpeechControls(`Reading ${speechState.index + 1} of ${speechState.chunks.length}`);
        };
        utterance.onpause = () => {
          if (sessionId !== speechSessionId) return;
          speechState.isPaused = true;
          updateSpeechControls('Reading paused');
        };
        utterance.onresume = () => {
          if (sessionId !== speechSessionId) return;
          speechState.isPaused = false;
          updateSpeechControls(`Reading ${speechState.index + 1} of ${speechState.chunks.length}`);
        };
        utterance.onend = () => {
          if (sessionId !== speechSessionId || !speechState.isPlaying) return;
          speechState.index += 1;
          speakNext();
        };
        utterance.onerror = (event) => {
          if (sessionId !== speechSessionId || event.error === 'canceled' || event.error === 'interrupted') return;
          console.warn('Browser speech failed:', event.error);
          speechState.isPlaying = false;
          speechState.isPaused = false;
          updateSpeechControls('Browser voice unavailable — use the transcript below');
        };

        try {
          window.speechSynthesis.speak(utterance);
        } catch (error) {
          console.warn('Browser speech could not start:', error);
          speechState.isPlaying = false;
          updateSpeechControls('Browser voice unavailable — use the transcript below');
        }
      };

      speakNext();
      return true;
    }

    if (speechPauseBtn) {
      speechPauseBtn.addEventListener('click', () => {
        if (!supportsBrowserSpeech() || !speechState.isPlaying) return;
        if (speechState.isPaused || window.speechSynthesis.paused) {
          speechState.isPaused = false;
          updateSpeechControls(`Reading ${speechState.index + 1} of ${speechState.chunks.length}`);
          window.speechSynthesis.resume();
        } else {
          speechState.isPaused = true;
          updateSpeechControls('Reading paused');
          window.speechSynthesis.pause();
        }
      });
    }

    if (speechRestartBtn) {
      speechRestartBtn.addEventListener('click', () => {
        if (speechState.text) startBrowserSpeech(speechState.text, speechState.title);
      });
    }

    if (speechStopBtn) {
      speechStopBtn.addEventListener('click', () => stopBrowserSpeech());
    }

    window.addEventListener('pagehide', () => stopBrowserSpeech({ hideControls: true }));

    // Existing hosted audio releases continue to use the regular audio player.
    function playAudio(url, title, transcript = '') {
      stopBrowserSpeech({ hideControls: true });
      hudTrackTitle.textContent = title;
      audioPlayerHud.classList.remove('hidden');
      showTranscript(transcript);

      if (!url) {
        clearAudioPlayer();
        mainAudioPlayer.classList.add('hidden');
        return;
      }

      mainAudioPlayer.classList.remove('hidden');
      mainAudioPlayer.src = url;
      mainAudioPlayer.load();
      mainAudioPlayer.play().catch(err => {
        console.warn("Autoplay blocked or play failed:", err);
      });
    }

    // --- STUDY GENERATION FORM ---
    const studyGenerateForm = document.getElementById('study-generate-form');
    const studySourceInput = document.getElementById('study-source-input');
    const studyGenerateBtn = document.getElementById('study-generate-btn');
    const studyGenerateStatus = document.getElementById('study-generate-status');

    if (studyGenerateForm) {
      studyGenerateForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const source = studySourceInput ? studySourceInput.value.trim() : '';
        if (!source) {
          if (studyGenerateStatus) {
            studyGenerateStatus.textContent = 'Please enter a YouTube link or book title.';
            studyGenerateStatus.classList.remove('hidden');
          }
          return;
        }
        if (studyGenerateBtn) {
          studyGenerateBtn.disabled = true;
          studyGenerateBtn.querySelector('span').textContent = 'Generating...';
        }
        if (studyGenerateStatus) {
          studyGenerateStatus.textContent = 'Consulting the archive...';
          studyGenerateStatus.classList.remove('hidden');
        }

        try {
          const { data: { session } } = await supabaseClient.auth.getSession();
          if (!session) {
            if (studyGenerateStatus) {
              studyGenerateStatus.textContent = 'Please sign in to generate content.';
            }
            return;
          }

          // Derive Primary Calibration from Natal Foundation (Highest Priority)
          const natalMonth = (birthMonthSelect ? birthMonthSelect.value : '') || localStorage.getItem('tdac_natal_month');
          const natalDay = (birthDaySelect ? birthDaySelect.value : '') || localStorage.getItem('tdac_natal_day');
          let primaryCalibration = null;
          if (window.TDAC_ASTROLOGY && natalMonth && natalDay) {
            primaryCalibration = window.TDAC_ASTROLOGY.buildPrimaryCalibration(natalMonth, natalDay);
          }

          const payload = {
            q1: 'Source material provided',
            q2: 'Source mode',
            q3: source,
            content_source: 'source_material',
            source_input: source,
            worldview: '',
            philosopher: '',
            first_name: session.user?.email?.split('@')[0] || 'Patron',
            honorary: 'Master',
            // Primary calibration anchors the psychological temperament & cadence
            primary_calibration: primaryCalibration,
            // The saved profile and selected lenses let Gemini tailor the reading
            // instead of treating every book request as an anonymous prompt.
            profile_context: profileContext.slice(0, 12000),
            active_worldviews: activeWorldviews.slice(0, 16)
          };

          const geminiRes = await fetch("https://frwjaixxlgthkgjtafhz.supabase.co/functions/v1/gemini", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });

          if (!geminiRes.ok) {
            const errText = await geminiRes.text();
            console.error('Gemini error:', errText);
            throw new Error(`Generation failed: ${geminiRes.status}`);
          }

          const data = await geminiRes.json();
          console.log('Gemini response:', data);
          
          // Save to localStorage like the main site does
          const existing = JSON.parse(localStorage.getItem('pending_source_materials') || '[]');
          const record = {
            id: Date.now().toString(),
            source_input: source,
            source_title: source,
            worldview: data.territory || 'becoming',
            bridge_line: data.bridge_line || '',
            expanded_text: data.expanded_text || '',
            territory: data.territory || 'becoming',
            created_at: new Date().toISOString()
          };
          existing.unshift(record);
          localStorage.setItem('pending_source_materials', JSON.stringify(existing));
          sourceMaterials = [record, ...sourceMaterials.filter((item) => item.id !== record.id)];

          // Save immediately as well as keeping the local recovery copy, so the
          // reading is available on the next sign-in and on another device.
          const { error: sourceSaveError } = await supabaseClient
            .from('user_contexts')
            .upsert({
              user_id: session.user.id,
              source_materials: sourceMaterials,
              updated_at: new Date().toISOString()
            }, { onConflict: 'user_id' });
          if (sourceSaveError) {
            console.warn('Could not save the reading to the vault:', sourceSaveError);
          } else {
            localStorage.removeItem('pending_source_materials');
          }

          if (studyGenerateStatus) {
            studyGenerateStatus.textContent = 'Generated! Your personalized reading is ready below.';
            studyGenerateStatus.classList.add('text-antique');
          }
          if (studySourceInput) studySourceInput.value = '';
          fetchUserReleases(session.user.id);
        } catch (err) {
          console.error(err);
          if (studyGenerateStatus) {
            studyGenerateStatus.textContent = `Error: ${err.message}`;
            studyGenerateStatus.classList.remove('text-antique');
          }
        } finally {
          if (studyGenerateBtn) {
            studyGenerateBtn.disabled = false;
            studyGenerateBtn.querySelector('span').textContent = 'Generate Reading';
          }
        }
      });
    }

    // --- NEW DRAG-AND-DROP & COPY LOGIC INTERACTION ---

    // 1. Copy Generator Prompt
    if (copyPromptBtn) {
      copyPromptBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(PROFILE_PROMPT_TEXT).then(() => {
          const span = copyPromptBtn.querySelector("span");
          const originalText = span.textContent;
          span.textContent = "Copied to Clipboard";
          copyPromptBtn.classList.add("border-antique", "bg-antique/20");
          setTimeout(() => {
            span.textContent = originalText;
            copyPromptBtn.classList.remove("border-antique", "bg-antique/20");
          }, 2200);
        }).catch(err => {
          console.warn("Clipboard copy operation failed:", err);
        });
      });
    }

    // 2. Process Dropped / Selected File
    const processDroppedMd = (file) => {
      if (!file) return;
      const isMd = file.name.endsWith('.md') || file.type === 'text/markdown' || file.type === 'text/plain';
      if (isMd) {
        const reader = new FileReader();
        reader.onload = (e) => {
          profileMdText.value = e.target.result;
          profileMdText.classList.remove("hidden");
          dropZoneIdle.classList.add("hidden");
          dropZone.classList.remove("border-dashed");
          dropZone.classList.add("border-antique/50", "bg-black/25");
          profileStatus.textContent = "Draft loaded (Save to apply)";
        };
        reader.readAsText(file);
      }
    };

    if (dropZone) {
      dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("border-antique", "bg-[#1c140f]");
      });
      dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("border-antique", "bg-[#1c140f]");
      });
      dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("border-antique", "bg-[#1c140f]");
        if (e.dataTransfer.files.length > 0) {
          processDroppedMd(e.dataTransfer.files[0]);
        }
      });
      dropZone.addEventListener("click", (e) => {
        if (e.target !== profileMdText && !revealPasteBtn.contains(e.target)) {
          mdFileInput?.click();
        }
      });
    }

    if (mdFileInput) {
      mdFileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
          processDroppedMd(e.target.files[0]);
        }
      });
    }

    if (revealPasteBtn) {
      revealPasteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        dropZoneIdle.classList.add("hidden");
        profileMdText.classList.remove("hidden");
        profileMdText.focus();
      });
    }

    // --- TAB SWITCHING LOGIC (ALIEN INC DESIGN SYSTEM) ---
    const tabBtnReadings = document.getElementById("tab-btn-readings");
    const tabBtnProfile = document.getElementById("tab-btn-profile");
    const sectionReadings = document.getElementById("section-readings");
    const sectionProfile = document.getElementById("section-profile");
    const quickOpenProfileBtn = document.getElementById("quick-open-profile-btn");

    function switchDashboardTab(target) {
      if (target === 'profile') {
        sectionReadings?.classList.add('hidden');
        sectionProfile?.classList.remove('hidden');
        tabBtnProfile?.classList.add('bg-alienGold', 'text-ink', 'border-alienGold', 'font-semibold');
        tabBtnProfile?.classList.remove('text-linen', 'border-transparent');
        tabBtnReadings?.classList.remove('bg-alienGold', 'text-ink', 'border-alienGold', 'font-semibold');
        tabBtnReadings?.classList.add('text-linen', 'border-transparent');
      } else {
        sectionProfile?.classList.add('hidden');
        sectionReadings?.classList.remove('hidden');
        tabBtnReadings?.classList.add('bg-alienGold', 'text-ink', 'border-alienGold', 'font-semibold');
        tabBtnReadings?.classList.remove('text-linen', 'border-transparent');
        tabBtnProfile?.classList.remove('bg-alienGold', 'text-ink', 'border-alienGold', 'font-semibold');
        tabBtnProfile?.classList.add('text-linen', 'border-transparent');
      }
    }

    tabBtnReadings?.addEventListener('click', () => switchDashboardTab('readings'));
    tabBtnProfile?.addEventListener('click', () => switchDashboardTab('profile'));
    quickOpenProfileBtn?.addEventListener('click', () => switchDashboardTab('profile'));

    function updateCalibrationSummaryPill() {
      const pill = document.getElementById('calibration-summary-pill');
      if (!pill) return;
      const natalMonth = (birthMonthSelect ? birthMonthSelect.value : '') || localStorage.getItem('tdac_natal_month');
      const natalDay = (birthDaySelect ? birthDaySelect.value : '') || localStorage.getItem('tdac_natal_day');
      const parts = [];
      if (natalMonth && natalDay) {
        parts.push("🎂 Natal Configured");
      }
      if (activeWorldviews.length > 0) {
        parts.push(`🔭 ${activeWorldviews.length} Lens${activeWorldviews.length > 1 ? 'es' : ''}`);
      }
      if (parts.length === 0) {
        pill.textContent = "⚡ Default Calibration (Customize)";
      } else {
        pill.textContent = parts.join(' · ') + " (Customize)";
      }
    }

    if (birthMonthSelect) {
      birthMonthSelect.addEventListener('change', updateCalibrationSummaryPill);
    }
    if (birthDaySelect) {
      birthDaySelect.addEventListener('change', updateCalibrationSummaryPill);
    }
