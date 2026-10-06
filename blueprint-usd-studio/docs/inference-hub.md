# Optional NVIDIA Inference Hub outlining

The [Hub tools sample](https://inference.nvidia.com/tools) uses
`https://inference-api.nvidia.com/v1/` with a bearer key and OpenAI-compatible
chat completions. Its example Llama 3.1 model is text-only. Choose a model with
documented image input support; availability depends on your Hub account.
The adapter uses Python's standard HTTP library, not an agent framework.

1. Upload a blueprint and finish local detection.
2. Open **AI-assisted outlines** under room review.
3. Enter your key in the password field. **List available models** requests IDs
   from `/v1/models`; it does not certify their vision capabilities.
4. **GPT 6.1 Sol** (`openai/openai/gpt-6.1-sol`) is preselected. Keep it or
   choose another image-capable model, confirm image sharing and request outlines.
   Listing models preserves your selection and warns if your key cannot see it;
   there is no automatic substitution. API requests that omit `model` use GPT 6.1
   Sol; explicit model IDs are honored, while blank/null IDs are rejected.
5. Read the evidence and assumptions, then show the proposals on the plan.
   They start unchecked. Confirm scale separately, inspect each proposal and
   explicitly select the outlines you want to accept.

The request sends only the current primary image, resized to at most 2048 pixels
on its longest side. Supporting PDFs, photos and existing room geometry are not
sent. The model returns normalized polygons, names, evidence and assumptions.
Coordinates are validated against the image; invalid or substantially overlapping
polygons are rejected. This validation does not establish architectural accuracy.
Room heights, measurements and doors are not inferred by this integration.
The fitted worked example must be uploaded as a new image project for AI tracing;
its dimension-based coordinate system cannot directly accept image polygons.

Accepted rooms retain provider, requested and reported model, prompt version,
source image hash/dimensions, time, basis and assumptions in reconstruction
evidence. No room is silently added and no calibration is changed. Existing
accepted rooms remain, so review possible duplicates before accepting more.
A changed project invalidates pending AI results.

Keys are transmitted only in Authorization headers and stay in the page's password
field between requests. They are not written to local/session storage, project
JSON or logs. The field is cleared after an outline request and when leaving the
page. **Clear key** clears it immediately. Provider error bodies are not exposed.
Only the fixed Hub endpoint is used and HTTP redirects are refused.

For remote users, serve the portal over HTTPS with a trusted certificate, typically
through an organization's reverse proxy forwarding to the app on loopback. Only
configure Uvicorn's forwarded-header trust for that proxy. The app does not trust
an arbitrary client's `X-Forwarded-Proto` header. Plain HTTP requests from LAN
clients cannot submit keys. On this machine, `http://127.0.0.1:8001` reaches the
same service and projects and allows local key use. Never paste a key into chat,
a URL, source code or a saved plan.

Tests mock Hub responses to check consent, transport security, request formatting,
geometry validation and secret-safe failures. A live call with your chosen vision
model and key is still required to verify account access and model output quality.
The DLSS analogy describes proposing missing information; this workflow does not
use DLSS frame generation or certify invented geometry as measured evidence.

A live check on 2026-10-06 authenticated against the Hub and ran
`nvidia/nvidia/nemotron-nano-12b-v2-vl` on the current apartment drawing. It returned
15 structurally valid proposals, including an incorrect room named “AVENUE VIEW”,
and missed spaces. No proposals were applied. This confirms connectivity and the
review path, not reconstruction accuracy or improvement over the local detector.
Model selection and held-out evaluation remain necessary before trusting geometry.

The same image and prompt were also tested with `openai/openai/gpt-6.1-sol`.
It returned 24 proposals and passed the existing inside/outside-point and area
checks for Bedroom 3, Kitchen, Bedroom 2 and Servant room. Nemotron passed none
of those four complete geometry checks. GPT 6.1 still included the lift, so its
proposals require scope review. This limited single-drawing comparison motivates
the preferred model; it is not a held-out accuracy benchmark or proof that every
boundary is correct. Both tests left the saved layout unchanged. The adapter
sends the same image/prompt regardless of model and records the selected model
in each accepted outline's evidence.
