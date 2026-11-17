---
name: Release process
description: The steps to tag and ship a lantern release
type: reference
---
1. Update `CHANGELOG.md` on a branch and merge it.
2. Tag `main` as `vX.Y.Z` and push the tag; CI builds the binaries.
3. Bump the pinned tag in tidepool in its own PR.
