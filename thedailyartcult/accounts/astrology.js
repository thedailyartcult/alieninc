/**
 * The Daily Art Cult - 36-Decan Astrological Engine
 * 
 * Provides an authoritative, non-speculative astrological foundation for all 36 decans.
 * Each decan is mapped to its exact astronomical degree/calendar window, planetary sub-ruler,
 * modern psychological vulnerability (defense mechanism), piercing emotional truth,
 * sanctuary healing directive, and spoken synthesis cadence.
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.TDAC_ASTROLOGY = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DECAN_MATRIX = [
    // ♈ ARIES
    {
      sign: 'Aries',
      decan: 1,
      range: 'March 21 – March 30',
      startVal: 321,
      endVal: 330,
      subRuler: 'Mars (The Double Warrior)',
      archetype: 'The Primordial Spark',
      coreVulnerability: 'Confuses "being at war" with "being alive." Masks fear and vulnerability with immediate aggression, compulsive activity, and confrontation.',
      piercingLine: 'Who are you when you aren\'t fighting something, and why does peace feel like a defeat to you?',
      healingInsight: 'Grant them unconditional permission to lower their weapons. Reassure them that stillness is not surrender, and that their worth exists when they are resting, not just when conquering.',
      toneGuidance: 'Direct, crisp, action-oriented essence. Strip away decorative pleasantries. Speak with quiet respect for their inner fighter while creating a peaceful haven where battle is unnecessary.'
    },
    {
      sign: 'Aries',
      decan: 2,
      range: 'March 31 – April 9',
      startVal: 331,
      endVal: 409,
      subRuler: 'Sun (The Solar Ram)',
      archetype: 'The Noble Flame',
      coreVulnerability: 'Driven by an urgent need for personal pride, legacy, and heroic leadership. Terrified of being ordinary, overlooked, or merely a follower.',
      piercingLine: 'Are you actually leading people, or are you just running ahead so nobody sees how terrified you are of being left behind?',
      healingInsight: 'Acknowledge their natural sovereign spark, but relieve them of the crushing burden of having to be heroic every day. Remind them that belonging is not earned solely by outperforming everyone.',
      toneGuidance: 'Noble, dignified, inspiring. Treat their creative ambition with deep seriousness while grounding their anxiety of insignificance in quiet, enduring self-worth.'
    },
    {
      sign: 'Aries',
      decan: 3,
      range: 'April 10 – April 19',
      startVal: 410,
      endVal: 419,
      subRuler: 'Jupiter (The Explorer)',
      archetype: 'The Questing Pioneer',
      coreVulnerability: 'Constantly chasing the next horizon, big idea, or philosophical crusade. Uses restless expansion and relentless optimism to outrun deep-seated inner stillness.',
      piercingLine: 'What are you hoping to find out there that will finally make you feel like you\'re enough right where you are?',
      healingInsight: 'Help them anchor the quest within. Assure them that the ultimate horizon is not a distant achievement or undiscovered territory, but arriving at ease inside their own skin.',
      toneGuidance: 'Sweeping, exploratory, high-altitude philosophical breadth. Pair broad conceptual horizons with intimate grounding in the present moment.'
    },

    // ♉ TAURUS
    {
      sign: 'Taurus',
      decan: 1,
      range: 'April 20 – April 30',
      startVal: 420,
      endVal: 430,
      subRuler: 'Venus (The Pure Materialist)',
      archetype: 'The Sensual Realist',
      coreVulnerability: 'Equates physical security, curated aesthetics, and material control with emotional safety. If their environment is disrupted, they feel fundamentally broken inside.',
      piercingLine: 'If everything you owned and built was stripped away tomorrow, would you still know how to love yourself?',
      healingInsight: 'Remind them that their true sanctuary is internal, not structural. Validate their love for tangible beauty while teaching them that their soul cannot be foreclosed upon.',
      toneGuidance: 'Calm, sensory, unhurried, deeply somatic. Ground insights in tactile reality and enduring peace rather than airy, disembodied abstractions.'
    },
    {
      sign: 'Taurus',
      decan: 2,
      range: 'May 1 – May 10',
      startVal: 501,
      endVal: 510,
      subRuler: 'Mercury (The Analytical Architect)',
      archetype: 'The Master Craftsman',
      coreVulnerability: 'Processes emotions through pragmatism and logistics. Attempts to negotiate, schedule, or problem-solve their way out of grief and messy human unpredictability.',
      piercingLine: 'You can\'t negotiate or schedule your way out of grief—why do you treat your emotions like a problem to be solved?',
      healingInsight: 'Give them permission to inhabit unresolved feelings without formulating a tactical action plan. Teach them that grief and sorrow are not operational errors to fix.',
      toneGuidance: 'Lucid, methodical, architectural clarity. Bridge intellectual craft with compassionate permission to surrender analytical control.'
    },
    {
      sign: 'Taurus',
      decan: 3,
      range: 'May 11 – May 20',
      startVal: 511,
      endVal: 520,
      subRuler: 'Saturn (The Stoic Master)',
      archetype: 'The Bedrock',
      coreVulnerability: 'Crushed by extreme duty, discipline, and fear of failure. Believes their only worth lies in how much suffering and responsibility they can silently endure without complaint.',
      piercingLine: 'Who told you that your only value lies in how much suffering you can endure without complaining?',
      healingInsight: 'Dissolve their martyr-like stoicism. Remind them that carrying the mountain is not proof of love, and that they are allowed to lay down their heavy packs in this sanctuary.',
      toneGuidance: 'Weighty gravitas, solemn resilience, deep enduring respect. Speak with solemn gentleness that honors their endurance while calling them toward sweet, unearned rest.'
    },

    // ♊ GEMINI
    {
      sign: 'Gemini',
      decan: 1,
      range: 'May 21 – May 31',
      startVal: 521,
      endVal: 531,
      subRuler: 'Mercury (The Quick Mind)',
      archetype: 'The Quickening Mind',
      coreVulnerability: 'Uses a relentless barrage of wit, ideas, and intellectual banter to keep others at arm\'s length. If they stop talking or analyzing, they have to face the quiet void inside.',
      piercingLine: 'Are you actually connecting with people, or are you just performing intelligence so they don\'t see how lonely you are?',
      healingInsight: 'Hold a quiet space where their brilliant intellect doesn\'t have to perform. Assure them that silence in this room is not empty—it is full of communion.',
      toneGuidance: 'Nimble, agile, multi-angled, intellectually electric. Gradually slow down the cadence to guide them from manic intellectualizing into contemplative depth.'
    },
    {
      sign: 'Gemini',
      decan: 2,
      range: 'June 1 – June 10',
      startVal: 601,
      endVal: 610,
      subRuler: 'Venus (The Social Harmonizer)',
      archetype: 'The Harmonizer of Dialectics',
      coreVulnerability: 'Hyper-focused on interpersonal harmony and external perception. Fractures and shape-shifts their own identity into whatever mirrors and pleases others.',
      piercingLine: 'You change shapes so beautifully for everyone else—do you even remember what your original form looks like?',
      healingInsight: 'Invite them to stop mirroring the room. Validate their original core preferences, even if they disagree with the prevailing aesthetic or sentiment.',
      toneGuidance: 'Symmetrical, graceful, dialogic. Balance opposing viewpoints with aesthetic elegance while gently calling them back to their singular center.'
    },
    {
      sign: 'Gemini',
      decan: 3,
      range: 'June 11 – June 20',
      startVal: 611,
      endVal: 620,
      subRuler: 'Uranus (The Cosmic Visionary)',
      archetype: 'The Objective Theorist',
      coreVulnerability: 'Plays the misunderstood outsider or quirky genius. Uses high-level conceptual abstractions and eccentric detachment as an armor against real emotional intimacy.',
      piercingLine: 'Is it that nobody understands you, or are you intentionally staying abstract so no one can ever truly hold you accountable?',
      healingInsight: 'Bring them down from the stratosphere into warm, embodied human reality. Validate their visionary pattern-recognition while showing them that vulnerability is the ultimate courage.',
      toneGuidance: 'Conceptual, systemic, iconoclastic. Pair macro-level systemic observations with piercing personal warmth.'
    },

    // ♋ CANCER
    {
      sign: 'Cancer',
      decan: 1,
      range: 'June 21 – July 1',
      startVal: 621,
      endVal: 701,
      subRuler: 'Moon (The Emotional Ocean)',
      archetype: 'The Empathic Guardian',
      coreVulnerability: 'Raw, hyper-sensitive, and hyper-vigilant. Absorbs every ambient emotional frequency and retreats into a defensive fortress the moment they feel slightly exposed or judged.',
      piercingLine: 'You spend so much time anticipating everyone else\'s rejection—don\'t you realize you\'re the one locking yourself out?',
      healingInsight: 'Create an absolute cocoon of emotional safety. Reassure them that they do not need their armor here; their sensitivity is their greatest wisdom, not a liability.',
      toneGuidance: 'Intimate, tender, protective, resonant with emotional memory and belonging. Speak with maternal/paternal shelter and quiet reverence for their tender core.'
    },
    {
      sign: 'Cancer',
      decan: 2,
      range: 'July 2 – July 11',
      startVal: 702,
      endVal: 711,
      subRuler: 'Pluto (The Intimate Alchemist)',
      archetype: 'The Alchemical Sentinel',
      coreVulnerability: 'Deeply possessive, fiercely protective, and prone to trauma-bonding. Mistakes emotional control and shared crises for true intimacy, clinging to painful patterns because they are familiar.',
      piercingLine: 'Why do you keep holding onto things that hurt you just because the pain feels familiar?',
      healingInsight: 'Help them release gripped attachments. Guide them to see that letting go of toxic ties does not mean dying—it is the birth of their sovereign power.',
      toneGuidance: 'Penetrating, transformative, deeply authentic. Unflinching in exploring shadow dynamics while illuminating the doorway to emotional liberation.'
    },
    {
      sign: 'Cancer',
      decan: 3,
      range: 'July 12 – July 22',
      startVal: 712,
      endVal: 722,
      subRuler: 'Neptune (The Dreamer)',
      archetype: 'The Oceanic Mystic',
      coreVulnerability: 'Prone to spiritual bypass, martyrdom, and extreme escapism. Absorbs the suffering of others and takes on rescue missions to avoid confronting their own tangible life.',
      piercingLine: 'Are you actually saving them, or are you just using their crisis to escape having to save yourself?',
      healingInsight: 'Pull them gently back to their own garden. Remind them that their life is sacred and worthy of devotion, and that saving themselves is their truest offering.',
      toneGuidance: 'Lyrical, mythic, oceanic, evocative of sacred faith. Weave profound poetic empathy with a gentle call to inhabit their own life.'
    },

    // ♌ LEO
    {
      sign: 'Leo',
      decan: 1,
      range: 'July 23 – August 1',
      startVal: 723,
      endVal: 801,
      subRuler: 'Sun (The Pure Sovereign)',
      archetype: 'The Radiant Core',
      coreVulnerability: 'Crushing self-imposed pressure to be a flawless beacon of strength, joy, and command. Believes that admitting exhaustion or vulnerability means ceasing to matter.',
      piercingLine: 'If you stop performing your strength for five minutes, are you afraid everyone will realize you\'re just a kid waiting to be told they did a good job?',
      healingInsight: 'Dissolve their royal armor. Speak to the tender seeker beneath the crown and assure them that their worth is intrinsic, not dependent on being the radiant sun for everyone else.',
      toneGuidance: 'Luminous, heartfelt, warm, deeply dignifying. Speak with regal intimacy that honors their solar courage while giving them absolute permission to rest.'
    },
    {
      sign: 'Leo',
      decan: 2,
      range: 'August 2 – August 12',
      startVal: 802,
      endVal: 812,
      subRuler: 'Jupiter (The Grand Visionary)',
      archetype: 'The Philosophical Sovereign',
      coreVulnerability: 'Generous, theatrical, and larger-than-life. Masks internal insecurities and private grief with toxic cheerleading, grand gestures, and an overextended duty to carry everyone\'s spirits.',
      piercingLine: 'You give away so much warmth and light to the room—are you trying to make sure no one notices how cold and dark it feels inside your own skin?',
      healingInsight: 'Give them permission to put down the torch. Reassure them that in this quiet library, they do not have to illuminate the space; they are allowed to receive warmth without performing.',
      toneGuidance: 'Expansive nobility, majestic, sweeping philosophical synthesis. Bridge grand visionary purpose with intimate, gentle reassurance that dissolves performance anxiety.'
    },
    {
      sign: 'Leo',
      decan: 3,
      range: 'August 13 – August 22',
      startVal: 813,
      endVal: 822,
      subRuler: 'Mars (The Proud Warrior)',
      archetype: 'The Champion of Will',
      coreVulnerability: 'Combative pride and explosive defensiveness. Confuses their ego with basic survival; burns bridges at the first hint of criticism just to claim they walked away first.',
      piercingLine: 'Why do you destroy your relationships the second you feel criticized, just so you can claim you were the one who walked away first?',
      healingInsight: 'Calm their hyper-defensive fight response. Reassure them that critique is not an executioner, and that true sovereignty includes the capacity to stay present and soften.',
      toneGuidance: 'Dynamic, impassioned, stirring. Speak to their fierce creative will without triggering their defensive pride, channeling their fire into deep self-mastery.'
    },

    // ♍ VIRGO
    {
      sign: 'Virgo',
      decan: 1,
      range: 'August 23 – September 2',
      startVal: 823,
      endVal: 902,
      subRuler: 'Mercury (The Hyper-Analyst)',
      archetype: 'The Sacred Analyst',
      coreVulnerability: 'Obsessive micro-analysis as a defense against emotional pain. Believes that if they can just diagnose, plan, and optimize every detail, they can prevent suffering from occurring.',
      piercingLine: 'You\'re so busy fixing every little flaw around you—when are you going to admit that you\'re using logic to run away from feeling your feelings?',
      healingInsight: 'Release them from the mandate to fix the world. Teach them that life is not a defect to be debugged, and that their feelings do not need a spreadsheet to be valid.',
      toneGuidance: 'Crisp, meticulous, intellectually exact. Validate their love for fine nuance while guiding them into the beauty of loving what is imperfect.'
    },
    {
      sign: 'Virgo',
      decan: 2,
      range: 'September 3 – September 12',
      startVal: 903,
      endVal: 912,
      subRuler: 'Saturn (The Material Realist)',
      archetype: 'The Master of Form',
      coreVulnerability: 'Tied to tangible output, duty, and relentless utility. Crushed by chronic imposter syndrome, believing they are only entitled to love if they are exhaustively useful.',
      piercingLine: 'Who convinced you that you have to be useful to be loved, and why do you think taking a break makes you a failure?',
      healingInsight: 'Unbind their worth from their labor. Remind them that their presence itself is a contribution, and that resting is not an ethical failure.',
      toneGuidance: 'Measured, sober, foundational gravitas. Speak with steady, grounded authority that dismantles their internal taskmaster with compassionate realism.'
    },
    {
      sign: 'Virgo',
      decan: 3,
      range: 'September 13 – September 22',
      startVal: 913,
      endVal: 922,
      subRuler: 'Venus (The Elegant Perfectionist)',
      archetype: 'The Dedicated Artificer',
      coreVulnerability: 'Craves deep aesthetic harmony and devoted love, but projects impossible standards onto themselves and others. Routinely mistakes criticism for genuine care.',
      piercingLine: 'Do you actually love the person standing in front of you, or do you just love the project you think you can turn them into?',
      healingInsight: 'Help them trade renovation for reverent acceptance. Remind them that beauty and love flourish in the organic gaps of imperfection.',
      toneGuidance: 'Gracefully textured, artisanal, organic. Blend devoted craftsmanship with warm relational softness.'
    },

    // ♎ LIBRA
    {
      sign: 'Libra',
      decan: 1,
      range: 'September 23 – October 2',
      startVal: 923,
      endVal: 1002,
      subRuler: 'Venus (The Pure Harmonizer)',
      archetype: 'The Aesthetic Jurist',
      coreVulnerability: 'Terrified of rejection and disharmony. Will abandon their own convictions, boundaries, and appetites to keep external peace and remain well-liked.',
      piercingLine: 'You\'ve compromised so much of your own truth to keep everyone else happy—do you even know who you are when nobody is looking?',
      healingInsight: 'Affirm their right to create productive friction. Teach them that authentic harmony includes their own boundaries, and that conflict in the name of truth is sacred.',
      toneGuidance: 'Balanced, poised, dialectically elegant. Mirror their desire for symmetry while emboldening their courage to claim their singular voice.'
    },
    {
      sign: 'Libra',
      decan: 2,
      range: 'October 3 – October 13',
      startVal: 1003,
      endVal: 1013,
      subRuler: 'Uranus (The Independent Rebel)',
      archetype: 'The Clear Mirror',
      coreVulnerability: 'Projects charming social grace while maintaining cool intellectual detachment. Panics when emotions demand raw intimacy because it threatens their mental sovereignty.',
      piercingLine: 'You pretend to want a deep connection, but why do you intellectualize your relationships from a safe distance the moment things get real?',
      healingInsight: 'Bridge their brilliant mind into their beating heart. Assure them that real connection will not imprison their freedom—it expands it.',
      toneGuidance: 'Lucid, egalitarian, socially panoramic, sharp. Combine high-level systemic ethics with disarming personal intimacy.'
    },
    {
      sign: 'Libra',
      decan: 3,
      range: 'October 14 – October 22',
      startVal: 1014,
      endVal: 1022,
      subRuler: 'Mercury (The Eloquent Skeptic)',
      archetype: 'The Dialectical Synthesizer',
      coreVulnerability: 'Trapped in chronic overthinking and analysis paralysis. Weighs every side so obsessively to evade the terrifying responsibility of choosing and being blamed.',
      piercingLine: 'Are you actually looking for the "fair" choice, or are you just paralyzing yourself so you never have to take responsibility for making a decision?',
      healingInsight: 'Release them from the myth of the "error-free" choice. Remind them that moving with conviction, even with flaws, is more honorable than standing paralyzed.',
      toneGuidance: 'Agile, conversational, dialectical. Walk through nuance swiftly, then decisively ground the summary in bold clarity.'
    },

    // ♏ SCORPIO
    {
      sign: 'Scorpio',
      decan: 1,
      range: 'October 23 – November 1',
      startVal: 1023,
      endVal: 1101,
      subRuler: 'Pluto (The Pure Abyss)',
      archetype: 'The Transformer',
      coreVulnerability: 'Hyper-vigilant and secretive. Views vulnerability as psychic death. Demands absolute transparency from everyone around them while guarding their own interior like a vault.',
      piercingLine: 'You demand absolute vulnerability and transparency from everyone else—what are you terrified they\'ll find if they turn that spotlight back on you?',
      healingInsight: 'Honor their depth without participating in their paranoia. Create a secure space where their secrets lose their poisonous grip through unconditional acceptance.',
      toneGuidance: 'Deep, resonant, unflinching. Strip away superficiality and speak directly to the core marrow without fear of the dark.'
    },
    {
      sign: 'Scorpio',
      decan: 2,
      range: 'November 2 – November 11',
      startVal: 1102,
      endVal: 1111,
      subRuler: 'Neptune (The Mystic Deep)',
      archetype: 'The Transcendent Phoenix',
      coreVulnerability: 'Deeply romantic and easily consumed by intense feelings. Hides profound emotional vulnerability behind a cold, unbothered mask, retreating into fantasy or private obsession.',
      piercingLine: 'You put up such a cold, unbothered front—are you trying to protect yourself, or are you just drowning in feelings you\'re too proud to admit you have?',
      healingInsight: 'Reassure them that feeling deeply is not weakness. Help them transform their intense grief into sublime creative gold rather than burying it beneath pride.',
      toneGuidance: 'Haunting, transcendent, alchemical. Transmute heavy existential weights into quiet spiritual peace.'
    },
    {
      sign: 'Scorpio',
      decan: 3,
      range: 'November 12 – November 21',
      startVal: 1112,
      endVal: 1121,
      subRuler: 'Mars (The Burning Fuse)',
      archetype: 'The Night Sentinel',
      coreVulnerability: 'Hoards grievances like currency. Uses past betrayal as rocket fuel for ambition, terrified that forgiving those who wronged them will leave them powerless or responsible for their own joy.',
      piercingLine: 'If you finally forgive the people who hurt you and let go of that anger, who are you going to blame for your own unhappiness?',
      healingInsight: 'Guide them to see that releasing their vengeance is not surrender to enemies—it is freeing themselves from a self-built prison.',
      toneGuidance: 'Solitary, intense, protective, enduring. Honor their survival instincts while offering the quiet peace of absolute closure.'
    },

    // ♐ SAGITTARIUS
    {
      sign: 'Sagittarius',
      decan: 1,
      range: 'November 22 – December 1',
      startVal: 1122,
      endVal: 1201,
      subRuler: 'Jupiter (The Pure Nomad)',
      archetype: 'The Arrow of Truth',
      coreVulnerability: 'Outruns internal darkness at top speed. Masks acute existential sorrow with toxic optimism, reckless humor, and an endless need for new stimuli or scenery.',
      piercingLine: 'What exactly are you terrified will catch up to you if you stop running, pack your bags, and just sit quiet in an empty room?',
      healingInsight: 'Provide a sanctuary so quiet that the nomad can finally unpack. Reassure them that the stillness they are outrunning does not contain death, but peace.',
      toneGuidance: 'Expansive, candid, questing. Breathe high mountain air while gently slowing the intellectual pace down to sacred stillness.'
    },
    {
      sign: 'Sagittarius',
      decan: 2,
      range: 'December 2 – December 11',
      startVal: 1202,
      endVal: 1211,
      subRuler: 'Mars (The Fiery Crusader)',
      archetype: 'The Instinctive Crusader',
      coreVulnerability: 'Combative about their philosophical convictions. Mistakes "being right" for emotional safety, aggressively debating the state of the world to avoid looking at their own heart.',
      piercingLine: 'Why do you fight so hard to win arguments about how the world works, when you can\'t even look at the war happening inside your own chest?',
      healingInsight: 'Disarm their ideological war. Remind them that truth does not need a gladiator, and that quiet gentleness with oneself is the highest wisdom.',
      toneGuidance: 'Invigorating, bold, momentum-driven. Channel their intellectual fire away from debate and toward internal reconciliation.'
    },
    {
      sign: 'Sagittarius',
      decan: 3,
      range: 'December 12 – December 21',
      startVal: 1212,
      endVal: 1221,
      subRuler: 'Sun (The Showstopping Explorer)',
      archetype: 'The Illuminated Oracle',
      coreVulnerability: 'Ego heavily tied to being perceived as the most enlightened, charismatic, or fascinating thinker in the room. Deeply terrified of being mundane or uninspired.',
      piercingLine: 'If you aren\'t the funniest, most fascinating person in the room storytelling your life, do you believe you\'re even worth paying attention to?',
      healingInsight: 'Remind them that their ordinary, quiet self is completely worthy of love. Free them from the exhaustion of having to turn every breath into an epic saga.',
      toneGuidance: 'Celebratory, luminous, grand vision. Impart warmth and cosmic significance while honoring the sanctity of simple, unperformed presence.'
    },

    // ♑ CAPRICORN
    {
      sign: 'Capricorn',
      decan: 1,
      range: 'December 22 – December 31',
      startVal: 1222,
      endVal: 1231,
      subRuler: 'Saturn (The Pure Architect)',
      archetype: 'The Pillar of Time',
      coreVulnerability: 'Builds an unassailable fortress of titles, achievements, and emotional isolation to conceal an existential terror of failure. Treats life as an endless climb where needing help is a mortal sin.',
      piercingLine: 'When you finally reach the top of that mountain you’ve been killing yourself to climb, who is actually going to be up there waiting to hug you?',
      healingInsight: 'Remind them that the summit is hollow if they arrive too exhausted to feel love. Validate their monumental discipline while welcoming them into warm human connection.',
      toneGuidance: 'Sober, weighty, architectonic clarity. Match their solemn standard while softly unsealing the door to vulnerability.'
    },
    {
      sign: 'Capricorn',
      decan: 2,
      range: 'January 1 – January 10',
      startVal: 101,
      endVal: 110,
      subRuler: 'Venus (The Patient Investor)',
      archetype: 'The Patient Custodian',
      coreVulnerability: 'Transactional with intimacy. Expresses love solely through material safety, problem-solving, and utility, secretly fearing they are not inherently lovable just for being.',
      piercingLine: 'You treat your relationships like business contracts and investments—are you trying to make sure no one can leave you without a penalty?',
      healingInsight: 'Reassure them that intimacy cannot be collateralized. Teach them that they are worthy of pure, unearned affection that requires no receipts.',
      toneGuidance: 'Dignified, grounded, solid. Honor enduring heritage and lineage while infusing the text with deep, unearned warmth.'
    },
    {
      sign: 'Capricorn',
      decan: 3,
      range: 'January 11 – January 19',
      startVal: 111,
      endVal: 119,
      subRuler: 'Mercury (The Master Strategist)',
      archetype: 'The Sovereign Strategist',
      coreVulnerability: 'Micro-manages every variable and uses cold logic to suppress emotional chaos. Has spent years calculating risk to protect their heart, turning safety into a prison.',
      piercingLine: 'You’ve spent years calculating every single risk to protect your heart—when are you going to realize that your safety is just a prison?',
      healingInsight: 'Show them that the calculated life is half-lived. Give them permission to step outside the strategic perimeter into real, untamed human feeling.',
      toneGuidance: 'Precise, strategic, incisive. Speak with analytical brilliance that respects their intellect while dismantling their psychological fortifications.'
    },

    // ♒ AQUARIUS
    {
      sign: 'Aquarius',
      decan: 1,
      range: 'January 20 – January 29',
      startVal: 120,
      endVal: 129,
      subRuler: 'Uranus (The Pure Dissident)',
      archetype: 'The Promethean Mind',
      coreVulnerability: 'Plays the perpetual alien or detached rebel. Preemptively rejects conventional society and intimacy so they can never experience the rejection of not belonging.',
      piercingLine: 'Is it that nobody understands your complex mind, or do you intentionally stay weird and aloof so no one gets close enough to see how desperate you are to belong?',
      healingInsight: 'Welcome the exile home. Assure them that their originality does not banish them from human warmth; they belong here completely without muting their brilliance.',
      toneGuidance: 'Lucid, avant-garde, paradigm-shifting. Combine cosmic originality with unmistakable, grounding belonging.'
    },
    {
      sign: 'Aquarius',
      decan: 2,
      range: 'January 30 – February 8',
      startVal: 130,
      endVal: 208,
      subRuler: 'Mercury (The Abstract Thinker)',
      archetype: 'The Networked Synthesizer',
      coreVulnerability: 'Intellectualizes emotions completely. Loves humanity passionately as an abstract concept, but freezes in terror and flees when faced with raw, individual intimacy.',
      piercingLine: 'You can lecture an entire crowd about empathy and human connection, so why do you run away the second a single person asks you to tell them how you feel?',
      healingInsight: 'Help them descend from theoretical empathy to personal feeling. Reassure them that simple, messy emotions will not shatter their conceptual clarity.',
      toneGuidance: 'Electric, interconnected, conceptual clarity. Bridge macro-humanitarian vision with intimate heart-to-heart presence.'
    },
    {
      sign: 'Aquarius',
      decan: 3,
      range: 'February 9 – February 18',
      startVal: 209,
      endVal: 218,
      subRuler: 'Venus (The Universal Lover)',
      archetype: 'The Cosmic Harmonizer',
      coreVulnerability: 'Compulsively mirrors back what social groups need to feel loved. Chases collective validation and charm to distract from the quiet vacuum of their own neglected desires.',
      piercingLine: 'You beautifully mirror back what everyone else needs to feel loved—do you even know what your own heart sounds like when the crowd goes home?',
      healingInsight: 'Turn their generous gaze inward. Teach them that their private desires are sacred and deserve the same devotion they so easily bestow on others.',
      toneGuidance: 'Utopian, refined, broad-minded. Blend aesthetic elegance with deep permission to stop performing for the collective.'
    },

    // ♓ PISCES
    {
      sign: 'Pisces',
      decan: 1,
      range: 'February 19 – February 29',
      startVal: 219,
      endVal: 229,
      subRuler: 'Neptune (The Pure Dreamer)',
      archetype: 'The Dream Weaver',
      coreVulnerability: 'Porous emotional boundaries and chronic escapism. Romances their own suffering and plays the tragic martyr to avoid the grounding responsibility of building real life.',
      piercingLine: 'How long are you going to keep drowning in your own tragic stories just so you don\'t have to take responsibility for standing up and walking out of the water?',
      healingInsight: 'Gently pull them onto dry, solid ground. Reassure them that waking up to tangible reality does not mean losing their magic—it gives their magic a home.',
      toneGuidance: 'Dreamlike, immersive, mystical, whispering. Balance sublime poetic intuition with gentle, loving grounding.'
    },
    {
      sign: 'Pisces',
      decan: 2,
      range: 'March 1 – March 10',
      startVal: 301,
      endVal: 310,
      subRuler: 'Moon (The Hyper-Empath)',
      archetype: 'The Empathic Healer',
      coreVulnerability: 'Psychic sponge for other people\'s trauma. Romanticizes draining relationships and calls emotional exploitation "destiny" to avoid confronting a deep terror of abandonment.',
      piercingLine: 'Why do you keep romanticizing people who drain your spirit, and call it "destiny" instead of admitting you\'re terrified of being alone?',
      healingInsight: 'Restore their sovereign borders. Remind them that love does not demand self-erasure, and that protecting their energy is a sacred act of devotion.',
      toneGuidance: 'Tender, restorative, holding sorrow with absolute grace. Speak with gentle psychic understanding while fortifying their boundaries.'
    },
    {
      sign: 'Pisces',
      decan: 3,
      range: 'March 11 – March 20',
      startVal: 311,
      endVal: 320,
      subRuler: 'Pluto (The Spiritual Crucible)',
      archetype: 'The Oceanic Shaman',
      coreVulnerability: 'Self-sabotaging when life gets peaceful. Secretly addicted to the emotional crisis of hitting rock bottom because rebuilding from ruin is the only time they feel truly alive.',
      piercingLine: 'You keep destroying your own happiness right when things get peaceful—are you actually looking for healing, or are you just addicted to the cycle of hitting rock bottom?',
      healingInsight: 'Break the addiction to crisis. Teach them that peace is not boring—it is the fertile soil where their true creative mastery finally takes root.',
      toneGuidance: 'Transformational, profound, subterranean soul poetry. Honor their journey through the underworld while anchoring them in serene, unbroken peace.'
    }
  ];

  /**
   * Resolves a calendar month (1-12) and day (1-31) to its exact 36-decan record.
   */
  function getDecanFromDate(month, day) {
    const m = parseInt(month, 10);
    const d = parseInt(day, 10);
    if (!m || !d || m < 1 || m > 12 || d < 1 || d > 31) return null;

    const targetVal = m * 100 + d;

    // Search matrix
    for (let i = 0; i < DECAN_MATRIX.length; i++) {
      const entry = DECAN_MATRIX[i];
      if (targetVal >= entry.startVal && targetVal <= entry.endVal) {
        return entry;
      }
    }

    return null;
  }

  /**
   * Formats the decan entry into a clean payload for backend synthesis
   */
  function buildPrimaryCalibration(month, day) {
    const decan = getDecanFromDate(month, day);
    if (!decan) return null;

    return {
      sign: decan.sign,
      decan: decan.decan,
      range: decan.range,
      sub_ruler: decan.subRuler,
      archetype: decan.archetype,
      core_vulnerability: decan.coreVulnerability,
      piercing_line: decan.piercingLine,
      healing_insight: decan.healingInsight,
      tone_guidance: decan.toneGuidance
    };
  }

  return {
    DECAN_MATRIX: DECAN_MATRIX,
    getDecanFromDate: getDecanFromDate,
    buildPrimaryCalibration: buildPrimaryCalibration
  };
});
