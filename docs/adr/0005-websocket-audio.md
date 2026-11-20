# 0005. Audio over WebSockets, not WebRTC

- Status: Accepted

## Context

The client records push-to-talk audio and plays back spoken replies, while both sides' captions
stream live. WebRTC is designed for continuous, peer-to-peer, low-latency media. It brings
signalling, STUN/TURN servers and a considerably larger operational surface.

## Decision

One WebSocket per session carries both JSON control events (state changes, captions, pending
actions) and binary audio frames:

- **Up:** each push-to-talk recording is one binary frame (WebM/Opus from the browser). The
  container is detected from its first bytes, not trusted from the client. Recordings over a
  size limit are refused.
- **Down:** the transcript comes back first as a caption, then the reply text, then the reply
  audio in two WAV frames: the opening words (at least four, a whole sentence or two) and then
  the rest of the reply. The first clip starts playing while the second is synthesized, and each
  clip ends with a short pause so the join sounds like a natural pause between sentences. An
  earlier version voiced every sentence separately and sounded choppy, and voicing the whole
  reply at once made the user wait for the full synthesis.
- **States:** `thinking`, `speaking` and `idle` status events drive the interface.

Memory extraction is deferred until the reply has been spoken, so it never competes with speech
synthesis for the CPU. The voice model is loaded and warmed up when the server starts.

Speech synthesis times on the development laptop swung from 0.6 to 12 seconds for the same
sentence. The cause was not the model: Windows 11 power throttling (EcoQoS) moves windowless
background processes such as a server onto the efficiency cores of hybrid Intel CPUs. The backend
now opts out of it at startup (`companion/performance.py`, Windows only). Voicing a full reply
dropped from 8 to 13 seconds to about 1.5 seconds, and the time from the end of the user's speech
to the first spoken word is now about 3.5 to 5 seconds, mostly spent waiting for the language
model.

## Consequences

- One protocol, one connection, and infrastructure FastAPI supports natively. It is easy to test
  with a scripted client.
- Not suitable for full-duplex conversation where the user interrupts mid-sentence. That is out of
  scope for v1 and would be the trigger to revisit this decision.
- The message protocol is versioned and documented, because the frontend and backend evolve
  together.
