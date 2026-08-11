---
name: newsc-digest
description: Build a daily insight digest for NewsC.
metadata:
  openclaw:
    skill: newsc-digest
---

# newsc-digest

Input: `{ "digest_date", "items": [...] }`

Output:

```json
{ "markdown": "# 今日洞察 ...", "highlights": ["..."] }
```
