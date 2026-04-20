# Fix Plan — OpenAI / Codex Auth Flow

## Summary

The OpenAI device-code (Codex) login and the "Test Connection" button are both
broken across `ParseUI.tsx` and `ChatPanel.tsx`. Three distinct bugs, one
cascading root cause from PR #48, plus pre-existing wiring issues.

---

## Bug 1 — `POST /api/auth/key` crashes with 500

**Symptom:** Test Connection icon turns red. Error:
`'RangeRequestHandler' object has no attribute '_read_body'`

**Root cause:** `_api_auth_key` (server.py line 2775) calls `self._read_body()`
which does not exist on `RangeRequestHandler`.

**Fix:** `python/server.py`, `_api_auth_key` method.

```python
# BEFORE (broken, lines 2775-2776):
body = self._read_body()
data = json.loads(body)

# AFTER:
data = self._read_json_body()
```

`_read_json_body()` reads raw body, decodes UTF-8, returns parsed dict — so
`json.loads()` is redundant. Every other POST handler in server.py already uses
`_read_json_body()`.

**Files:** `python/server.py`
**PR:** #49 (already open, covers this fix)

---

## Bug 2 — "Sign in with Codex" button is a dead stub (ParseUI.tsx)

**Symptom:** Clicking "Sign in with Codex" on the OpenAI form instantly shows
"connected" state without ever running the OAuth device-code flow. No user_code
is displayed, no polling occurs, no tokens are exchanged.

**Root cause:** Line 630 in `ParseUI.tsx`:
```tsx
onClick={() => { setProvider('openai'); setView('connected'); }}
```
This just flips UI state — it never calls `startAuthFlow()` or `pollAuth()`.

**Fix:** `src/ParseUI.tsx` — wire the "Sign in with Codex" button to the actual
OAuth device-code flow:

1. Add OAuth state to `AIChat`:
   ```tsx
   const [oauthPending, setOauthPending] = useState(false);
   const [oauthCode, setOauthCode] = useState('');
   const [oauthUri, setOauthUri] = useState('');
   const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
   ```

2. Add cleanup on unmount:
   ```tsx
   useEffect(() => {
     return () => { if (pollRef.current) clearInterval(pollRef.current); };
   }, []);
   ```

3. Create `handleCodexSignIn`:
   ```tsx
   const handleCodexSignIn = async () => {
     setOauthPending(true);
     setTestMessage('');
     try {
       await startAuthFlow();
       // startAuthFlow stores device_auth_id on the server; get_auth_status
       // returns user_code + verification_uri when a flow is active
       const status = await getAuthStatus();
       if (status.user_code) {
         setOauthCode(status.user_code);
         setOauthUri(status.verification_uri ?? '');
       }
       // Poll every 5s until authenticated
       pollRef.current = setInterval(async () => {
         try {
           const s = await getAuthStatus();
           if (s.authenticated) {
             if (pollRef.current) clearInterval(pollRef.current);
             pollRef.current = null;
             setOauthPending(false);
             setProvider('openai');
             setView('connected');
           }
         } catch { /* keep polling */ }
       }, 5000);
     } catch (err) {
       setOauthPending(false);
       setTestStatus('error');
       setTestMessage(err instanceof Error ? err.message : 'OAuth start failed.');
     }
   };
   ```

4. Replace the dead button (line 629-634):
   ```tsx
   <button
     onClick={handleCodexSignIn}
     disabled={oauthPending}
     className="..."
   >
     {oauthPending ? 'Waiting for sign-in...' : 'Sign in with Codex'}
   </button>
   ```

5. Below the button, show the device code when `oauthPending && oauthCode`:
   ```tsx
   {oauthPending && oauthCode && (
     <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
       <div className="text-[11px] text-slate-500 mb-1">Enter this code:</div>
       <div className="text-lg font-mono font-bold tracking-widest text-slate-900">
         {oauthCode}
       </div>
       {oauthUri && (
         <a href={oauthUri} target="_blank" rel="noreferrer"
            className="mt-1 block text-[11px] text-indigo-600 hover:underline">
           {oauthUri}
         </a>
       )}
       <div className="mt-2 text-[10px] text-slate-400">Waiting for confirmation...</div>
     </div>
   )}
   ```

6. Add `import { getAuthStatus, startAuthFlow, saveApiKey } from '../../api/client'`
   (or wherever `AIChat` sources its imports — check the actual import block at
   the top of ParseUI.tsx).

**Files:** `src/ParseUI.tsx`

---

## Bug 3 — ChatPanel OAuth polls wrong endpoint for user_code

**Symptom:** `handleStartOAuth` in `ChatPanel.tsx` starts the flow but the
device code never appears. `oauthInfo.user_code` stays undefined.

**Root cause:** Lines 75-78 of `ChatPanel.tsx`:
```tsx
await startAuthFlow();
const status = await pollAuth();  // ← WRONG
if (status.user_code) { ... }
```

`pollAuth()` calls `POST /api/auth/poll` → `poll_device_auth()` which returns
`{status: "pending"}` — it does **not** return `user_code` or `verification_uri`.

Those fields are returned by `GET /api/auth/status` → `get_auth_status()` when
a flow is active.

**Fix:** `src/components/annotate/ChatPanel.tsx`, `handleStartOAuth`:

```tsx
// BEFORE (broken):
await startAuthFlow();
const status = await pollAuth();
if (status.user_code) {
  setOauthInfo({ user_code: status.user_code, verification_uri: status.verification_uri });
}

// AFTER:
await startAuthFlow();
const status = await getAuthStatus();  // ← correct endpoint
if (status.user_code) {
  setOauthInfo({ user_code: status.user_code, verification_uri: status.verification_uri });
}
```

Also fix the polling loop (lines 81-92) to use `getAuthStatus()` instead of
`pollAuth()`:

```tsx
pollRef.current = setInterval(async () => {
  try {
    const s = await getAuthStatus();  // ← was pollAuth()
    if (s.authenticated) {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
      setAuthState("authenticated");
    }
  } catch {
    // keep polling
  }
}, 5000);
```

**Files:** `src/components/annotate/ChatPanel.tsx`

---

## Bug 4 — `handleTestConnection` uses wrong provider for xAI

**Symptom:** "Test Connection" on the xAI form sends `provider: 'openai'`
instead of `'xai'`.

**Root cause:** Line 304 in `ParseUI.tsx`:
```tsx
await saveApiKey(apiKey.trim(), provider ?? 'openai');
```

When on `form-xai`, `provider` state is already set to `'xai'` (line 323), so
this actually works. However, the fallback `'openai'` is misleading and would
break if `provider` were ever null at that point.

**Fix:** No code change strictly required — `provider` is set before the form
renders. But consider tightening the fallback:
```tsx
await saveApiKey(apiKey.trim(), provider ?? (view === 'form-xai' ? 'xai' : 'openai'));
```

**Files:** `src/ParseUI.tsx` (optional hardening)

---

## Checklist

- [ ] Fix Bug 1: `_read_body` → `_read_json_body` in server.py (PR #49)
- [ ] Fix Bug 2: Wire "Sign in with Codex" to real OAuth device-code flow
- [ ] Fix Bug 3: `pollAuth()` → `getAuthStatus()` in ChatPanel OAuth flow
- [ ] Fix Bug 4 (optional): Harden provider fallback in handleTestConnection
- [ ] Add `startAuthFlow` + `getAuthStatus` imports to ParseUI.tsx
- [ ] Run `npm run test -- --run` (floor ≥132) + `tsc --noEmit`
- [ ] Delete this plan file before merge

## Impact

- Bug 1 blocks all key-save and test-connection flows (both providers)
- Bug 2 makes Codex/OpenAI OAuth completely non-functional in ParseUI
- Bug 3 makes Codex/OpenAI OAuth non-functional in ChatPanel
- No API contract changes. No new server endpoints needed.
