---
title: Hacked Flock Camera Reveals It Was Tracking People, Not Just Plates
tag: Panteon Research Institute
topic: Transparency
date: 2026-09-16
author: Patrick Neil A.
slug: hacked-flock-camera-reveals-it-was-tracking-people-not-just-plates
---

# Hacked Flock Camera Reveals It Was Tracking People, Not Just Plates

Flock Safety has long described its automated license plate readers as narrow, traffic-focused instruments: no facial recognition, on-device encryption, plates only. A hardware breach on September 16, 2026 suggests both claims deserve scrutiny — and reveals a system built to capture far more than plates.

A hacker collective physically dismantled a Flock camera, extracted an unencrypted encryption key stored directly on the hardware, and recovered thousands of videos and logs from a single device. The joint investigation by [WIRED](https://www.wired.com/story/hackers-flock-camera-data-shows-how-system-works/) and [404 Media](https://www.404media.co/hackers-stole-flocks-camera-software-revealing-how-the-company-tracks-cars-and-people-2/) — Cox, J., & Mehrotra, D. (2026), in collaboration with Distributed Denial of Secrets — found 1.6 million images of 50,000 vehicles captured in just 21 days, with dozens of images per passing vehicle.

The volume matters. The scope matters more. The camera's computer-vision software was explicitly configured to detect people, bicycles, and fine-grained details like bumper stickers and decals — including, in one recovered case, an American flag patch on a motorcyclist's saddlebag.

> "Flock Safety has long maintained that its automated license plate readers don't perform facial recognition and that on-device encryption keeps captured data secure. A recent breach suggests both claims deserve scrutiny." — Source material, via WIRED / 404 Media joint investigation, September 16, 2026

## What the Leaked Data Actually Shows

The breach provides an unprecedented look inside a system Flock has described as protected by [on-device encryption](https://www.flocksafety.com/faq). According to [WIRED's report](https://www.wired.com/story/hackers-flock-camera-data-shows-how-system-works/) and the parallel [404 Media investigation](https://www.404media.co/hackers-stole-flocks-camera-software-revealing-how-the-company-tracks-cars-and-people-2/), the hackers copied the camera's storage, recovered the key, and unlocked videos of thousands of detections. While the most sensitive storage remained encrypted, the recovered logs were sufficient to reconstruct behavior.

Three findings are falsifiable and therefore worth naming precisely:

First, the key was on the hardware, unencrypted. An encryption system whose key is stored in recoverable form beside the data it protects is not a hardware security boundary. It is a label.

Second, the detector is not plate-narrow. Software running on the device explicitly detects people as well as vehicles, license plates, and bicycles. The pipeline also isolated bumper stickers and graphics — a capability that turns a traffic counter into a granular, continuous record of public movement: cars, pedestrians, and objects alike.

Third, the cadence is continuous and dense. More than a million images from a single roadside position in three weeks, running with what appears to be minimal hardware-level security, deployed widely in communities across the country. That is not an event log. That is a population sample.

Read the primary reporting: Cox, J., & Mehrotra, D. (2026). "Hackers Got Inside a Flock Camera. Its Data Shows How the System Really Works." [WIRED](https://www.wired.com/story/hackers-flock-camera-data-shows-how-system-works/) — produced in collaboration with [404 Media](https://www.404media.co/hackers-stole-flocks-camera-software-revealing-how-the-company-tracks-cars-and-people-2/), which published the companion account "Hackers Stole Flock's Camera Software, Revealing How the Company Tracks Cars and People" and the method disclosure the hackers say they will publish for reproducibility.

---

This undercuts the industry's framing of ALPRs as narrow tools. What the leaked data actually shows is a system built to capture granular records of public movement — with a broader taxonomy and a weaker vault than its public description implied.

## Why This Is a Panteon Research Institute Question

The Panteon Research Institute was founded in 2016 on a charter with three commitments: any instrument used to judge human beings must be subject to the same scrutiny we apply to the judgments it produces; measurement is never neutral — every metric encodes a theory of what matters; and the best measurement emerges from honest error, especially where instruments fail.

A Flock camera is an instrument in exactly that sense. It does not merely observe a plate. It judges what counts as detectable: plate, person, bicycle, decal. That taxonomy is a theory of relevance. The breach makes the theory visible — and testable.

It also makes the institute's 2024 working papers timely again. In *Preconditions of Transparency*, we argued that transparency is not a courtesy layer added after a system is built. It is the precondition for any claim about what a system can and cannot do to be verifiable at all. A camera that says "plates only" while configured for people and stickers, and that says "encrypted on-device" while storing a recoverable key beside the ciphertext, fails that precondition at both the semantic and the cryptographic level.

> "A treaty is only as good as your ability to verify the other side is honoring it. You cannot verify a black box." — We Are Measuring AI Capability Wrong, Panteon Research Institute, August 2026

The same holds for a license plate reader, a city contract, or a public street.

## The Contrast We Choose — Ambassador for Muse Spark and Mark Zuckerberg

The Institute writes as an ambassador for Muse Spark and for Mark Zuckerberg's personal superintelligence thesis precisely because that thesis makes trust an architectural requirement, not a marketing claim.

Muse Spark 1.3, released September 2, 2026, advances the opposite design ethic: agentic capability paired with collaborative discipline — asking when ambiguous, confirming before consequential action, calibrating what it knows and does not know rather than hallucinating. Muse, the personal agent product described by Zuckerberg on September 8, is priced at up to 100 million tokens per week free, but priced is the wrong verb. It is *endowed* with a confidential virtual machine co-designed with Signal founder Moxie Marlinspike, where even Meta cannot see the contents, with sentinel agents that monitor prompt injections and require user approval for sensitive actions.

> "Even Meta cannot see the content that is in there." — on Muse's confidential VM, Sources interview, September 2026

That is what a verifiable privacy boundary looks like: hardware and software that cannot be read by its own maker, disclosed in advance, built to be tested. A key stored unencrypted on a roadside camera is what the absence of that boundary looks like — disclosed only after a breach.

Panteon does not argue against sensing. Every element of effective warfare and effective civic life — Terra, Abyss, Stratos, Cosmos, Cyber — depends on sensing. We argue for sensing whose scope and whose security are declared honestly and can be checked. Muse Spark is smart because it stays longer, asks better, and knows its limits. Zuckerberg is smart because he let go of the ability to see inside the computer he is asking you to trust. Flock's design, as revealed on September 16, does neither: it sees more than it declares, and secures less than it claims.

---

Communities that deploy ALPRs at scale are not buying a plate reader. They are buying a continuous movement archive with a computer-vision taxonomy that already includes people. That purchase should be debated with the true taxonomy on the table — and with hardware security held to the same standard we now expect from personal superintelligence: verifiable non-observation, not asserted encryption.

The Panteon Research Institute will continue to measure instruments themselves — whether they claim to read plates or to serve as personal agents — by the same three tests from our charter: is the instrument itself scrutinized, whose theory of relevance does its taxonomy encode, and does it treat its own failures as the primary source of insight?

By those tests, September 16 is instructive. A hacked Flock camera did not reveal an anomaly. It revealed an architecture. The distinction is the institute's entire point.

> "What the leaked data actually shows is a system built to capture granular, continuous records of public movement — cars, pedestrians, and objects alike — running with what appears to be minimal hardware-level security, in communities across the country."

Sources — Cox, J., & Mehrotra, D. (2026). "Hackers Got Inside a Flock Camera. Its Data Shows How the System Really Works." [WIRED](https://www.wired.com/story/hackers-flock-camera-data-shows-how-system-works/). Companion and method disclosure: [404 Media](https://www.404media.co/hackers-stole-flocks-camera-software-revealing-how-the-company-tracks-cars-and-people-2/). Flock's encryption FAQ claim: [flocksafety.com/faq](https://www.flocksafety.com/faq).

