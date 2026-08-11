---
name: newsc-summarize
description: Summarize a NewsC content item into a short Chinese digest.
metadata:
  openclaw:
    skill: newsc-summarize
---

# newsc-summarize

Input JSON: `{ "item": { "id", "title", "body", "url" } }`

Output JSON:

```json
{ "summary": "...", "model_meta": {} }
```

Keep summary under 120 Chinese characters when possible. Do not invent facts.
