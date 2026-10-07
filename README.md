# OpenAI Decisions for Home Assistant

A Home Assistant action, `openai_decisions.decide`, for OpenAI's
[Decisions API](https://developers.openai.com/api/docs/guides/decisions). You ask questions
about text and camera frames and get back **probabilities**, not free text:

| Question type | You get back |
|---|---|
| `predicate` (default) | `probability` that the statement is true, 0–1 |
| `choice` | the picked `choice`, per-option `probabilities`, `confidence` |
| `score` | probability-weighted `score` across ordered levels, `probabilities`, `confidence` |

Decisions answers in a fraction of a second, which suits automations such as "is a package on
the porch?". It costs $0.10 per 1M input tokens and output is free, so one camera frame costs
about $0.0001.

## Install

1. HACS → ⋮ → Custom repositories → add `https://github.com/mattvv/openai-decisions-home-assistant`
   (type *Integration*), then download **OpenAI Decisions** and restart Home Assistant.
2. Settings → Devices & services → Add integration → **OpenAI Decisions** → paste an
   [OpenAI Platform API key](https://platform.openai.com/api-keys).

The API is billed per use through the OpenAI Platform. ChatGPT Plus/Pro subscriptions don't
cover it, and the account needs prepaid credits. With no credits, calls fail with
`OpenAI quota or rate limit: You have no credits remaining`.

## The action

```yaml
action: openai_decisions.decide
data:
  camera_entity_id: camera.doorbell_porch   # one or more; a fresh frame from each is sent inline
  text: >-                                  # optional context sent with the images
    Doorbell camera frame of a front porch. Two doormats and a lantern are permanent.
  questions:
    - name: package
      instructions: Is a delivered package (box, mailer, bag) sitting on the porch floor?
    - name: carrier
      type: choice
      instructions: Which courier is visible, if any?
      choices: [none, usps, ups, fedex, amazon, other]   # strings or {value, description}
response_variable: seen
```

Response:

```yaml
answers:
  package: {type: predicate, probability: 0.94}
  carrier:
    type: choice
    choice: none
    confidence: 0.97
    probabilities: [{value: none, probability: 0.98}, ...]
model: gpt-6-luna
usage: {...}
elapsed_ms: 180
```

So in a template you'd use `{{ seen.answers.package.probability > 0.8 }}`. An answer can come
back as `type: refusal` with no probability, so give your templates a default.

| Field | |
|---|---|
| `questions` | required. Each has `name`, `instructions`, and optionally `type`. `choice` needs `choices`; `score` needs `levels`, ordered lowest to highest. |
| `text` | context, or the whole input when there are no images |
| `camera_entity_id` | cameras to snapshot |
| `image_path` | local image files (must be in `allowlist_external_dirs`) |
| `model` | default `gpt-6-luna`, currently the only Decisions model |
| `timeout` | seconds, default 15 |
| `config_entry_id` | which key to use, if you set up more than one |

Pick thresholds from labelled examples of your own camera. A valid probability is not
necessarily a correct one.

## Development

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
```
