# The browser client — two paragraphs for the submission

*(Owner B. Drop straight into SUBMISSION.md; trim the second paragraph first if space is
tight.)*

---

Airlock intercepts the paste itself, not the network request that follows it. A Manifest
V3 content script binds `paste`, `beforeinput`, `drop` and file-input `change` on
`document` in the **capture phase** at `document_start`, in every frame — never on a
selector, because ProseMirror and Lexical rebuild their nodes constantly and a
selector-bound listener ends up attached to something that no longer exists. Extraction
of `text/plain`, `text/html` and `items[].getAsFile()` is entirely synchronous, because
the default action of a trusted paste runs the moment the handler returns: a single
`await` above `preventDefault()` hands the payload to the page. The characters are
therefore removed from the event and held in the extension before the site's own
JavaScript ever sees them, which is why `bytes_egressed: 0` on a block is a literal
statement rather than a claim. On `allow` the text is replayed with
`document.execCommand('insertText')`, falling back to the React prototype-setter —
never by assigning `.value`, which React reads past, and never by dispatching a
synthetic `ClipboardEvent`, which is `isTrusted: false`, performs no default action and
fails silently.

Every network call is made from the service worker, and that is a constraint rather than
a preference: `fetch` to `127.0.0.1` from a content script on an `https://` page is
subject to Chrome's Local Network Access checks, while the same call from the extension's
service worker is not. The content script reaches it over `chrome.runtime.sendMessage`,
guarded by a `chrome.runtime.id` check so an extension reload under an open tab degrades
to a direct `fetch` with `targetAddressSpace: 'local'` instead of hanging. Every failure
path — client timeout at 2500 ms, unreachable inspector, invalidated extension context,
undecodable image, an unrecognised response body — resolves to the same fail-closed
verdict, `{action: 'block', label: 'airlock_unavailable'}`, because deny-by-default is
the product and so it has to be the failure mode too. Below all of that sits a
`declarativeNetRequest` session rule that blocks the upstream conversation endpoint
outright; it is enforced in the network stack, so it still holds with the service worker
asleep and the content script broken. That is a switch rather than an inspector, which is
exactly why it is the last line and not the first.

---

## Notes for whoever pastes this in

- **Do not claim the extension has been demonstrated end to end.** At the time of
  writing it has not: `overlay.js` injected manually over CDP runs clean and builds its
  shadow root, but manifest-driven injection and the paste interception itself are
  unverified. Chrome 151 refuses `--load-extension` from the command line, so the check
  needs the `chrome://extensions` UI and about twenty seconds of a human's attention.
  If it passes before submission, say so; if nobody runs it, describe the mechanism and
  say the measured numbers come from the HTTP path, which is true either way.
- The FP-rate harness never goes through Chrome — it posts to `/v1/inspect` directly
  (NFR-T5). Nothing in the reported numbers depends on the extension working.
- `clipboardRead` is deliberately **not** requested. It would put "Read data you copy and
  paste" on the install prompt, which is the wrong first impression for a privacy
  product, and a trusted paste event already carries the data.
