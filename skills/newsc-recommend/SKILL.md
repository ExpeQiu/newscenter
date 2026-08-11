---
name: newsc-recommend
description: Recommend NewsC items using user mark signals.
metadata:
  openclaw:
    skill: newsc-recommend
---

# newsc-recommend

Input: `{ "user_signals", "candidates", "as_of" }`

Output:

```json
{ "items": [{ "id": "...", "score": 0.9, "reason": "..." }] }
```

Return at most 7 items.
