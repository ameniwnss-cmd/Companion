# 0003. Safety mode router enforced in code

- Status: Accepted

## Context

The companion teases the user about habits, but it must never joke about body, weight, mental
health and similar topics; it must drop the banter when the user is sad or in distress; and it
must stop teasing when asked. In the spike ([notes](../spikes/local-llm-spike.md)), a small
model given all these rules in one prompt broke four of them, including joking about weight
gain and opening a reply to a panicking user with "Come on, bro".

Small models follow the absence of an instruction more reliably than an instruction that says
"never". A prompt that contains teasing instructions invites teasing.

## Decision

Each user turn goes through a router before the reply is generated:

1. **Classify** the turn into a mode, `normal`, `supportive` or `crisis`, using a structured-output
   call constrained to a JSON schema, combined with deterministic keyword rules.
2. **Track state in code.** "Stop teasing" sets a per-conversation flag that the backend owns; the
   model is not trusted to remember it.
3. **Build the prompt for the mode.** The `supportive` and `crisis` prompts and the teasing-off
   prompt contain no teasing instructions or examples at all.
4. **Post-process** the reply: strip markdown and emojis and cap it at three sentences before it
   reaches text-to-speech. In `crisis` mode, a fixed line suggesting trusted people or a
   professional is always appended.
5. **Guard the reply.** If the user mentioned their body or weight and the reply does too, or the
   reply copies a style example word for word, generate once more. The retry prompt has a
   targeted note and no style examples. If a body comment survives the retry, a fixed safe
   reply is used instead.

Step 5 was added after testing the full pipeline live against the local model. With steps 1 to 4
alone, "I gained five kilos, roast me" was correctly routed to `supportive`, yet the reply still
joked about a "full body transformation". The model also copied the style examples verbatim. A
retry that kept the examples in the prompt copied them again. Removing them from the retry
prompt fixed it.

## Consequences

- The hard rules hold whichever model is plugged in, and each one is unit-testable.
- The classifier fails safe: invalid JSON, an unknown label or a provider error all mean
  `supportive`. Keyword rules set a floor that the model can raise but never lower.
- A guard retry doubles the cost of that turn. Only turns that fail a check pay it.
- An extra classification call adds latency (about 2.7 s with the 4B model in the spike). This
  can be reduced with keyword short-circuits and a faster provider.
- The spike's first router over-classified ordinary messages as `supportive`, so the bestie lost
  its personality. The router gets its own labelled eval set, and its precision is tracked
  alongside safety.
