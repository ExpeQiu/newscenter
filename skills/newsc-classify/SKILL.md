---
name: newsc-classify
description: Classify a NewsC item into category and tags.
metadata:
  openclaw:
    skill: newsc-classify
---

# newsc-classify

If `category_locked` is true, return the existing category and `"skipped": true`.

Output:

```json
{ "category": "科技", "tags": ["AI"], "confidence": 0.8 }
```
