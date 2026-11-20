# 0002. Swappable AI providers behind small interfaces

- Status: Accepted

## Context

The app depends on four AI capabilities: a language model (conversation and tool calls),
speech-to-text, text-to-speech, and embeddings for memory search. The project must cost nothing
to run, tests and CI must not need network access or API keys, and the best provider for each
capability will change over time.

An early spike ([notes](../spikes/local-llm-spike.md)) showed that a 4B local model
running on a 6 GB laptop GPU answers in about 3 seconds and makes correct tool calls, but breaks
the personality's safety rules when it relies on the prompt alone.

## Decision

Each capability is a small Python `Protocol` (for example `LLMProvider`, `SpeechToText`) with
several implementations, chosen by configuration:

| Capability    | Default (demo)            | Offline fallback          | Kept ready                  | Tests |
| ------------- | ------------------------- | ------------------------- | --------------------------- | ----- |
| Language model | Groq free tier            | Ollama, Qwen3 4B Instruct | Anthropic Claude            | Fake  |
| Speech-to-text | Groq Whisper (free tier)  | Local Whisper (planned)   |                             | Fake  |
| Text-to-speech | Kokoro, local ONNX model  |                           |                             | Fake  |
| Embeddings     | Ollama `all-minilm` (local) |                         |                             | Fake  |

The rest of the code depends only on the interfaces. No LLM orchestration framework is used: the
conversation loop is small enough to own and test directly.

## Consequences

- Unit, integration and end-to-end tests run on fakes: deterministic, free and offline.
- Moving to another provider is a new adapter plus a config value, not a rewrite.
- Each adapter has to translate its provider's tool-calling format into one internal shape. That
  translation is covered by adapter tests.
- Behaviour that must not depend on model quality (safety, formatting, dates) is enforced in code
  rather than in prompts; see [0003](0003-safety-mode-router.md).
