// platforms/shared/api.js — extracted from admin.html 2026-08-31
// Shared API helper for all platforms. Shell already inlines this; platforms should import via global  or .
// Keep in one place so LLMs know the contract without reading whole admin.html.
// Usage: const data = await api('/spinal-craker/object-types'); // throws on non-2xx, auto-injects authToken, handles 401 refresh
// Contract: API_BASE = '/api/v1', timeout 15000ms default, retries 401 once via supabase refresh.
// See admin.html:5186 const API_BASE and ~5420 async function api for canonical implementation.
// This file documents the contract; shell inlines the real function for now. Future: <script src="platforms/shared/api.js"> replaces inline.

export const API_BASE = '/api/v1';
export const API_TIMEOUT_MS = 15000;

// Re-exported for docs — do not duplicate logic here; shell owns the live .
// Platforms that are loaded as ESM can: import { api } from '../shared/api.js' after shell exposes it.
