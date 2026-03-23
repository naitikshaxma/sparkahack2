# Release Checklist v1.0

## Code and Quality

- [ ] All frontend and backend tests pass
- [ ] No critical lint or type errors
- [ ] Build artifacts generated successfully
- [ ] Security checks and secret scans pass

## Product and Demo

- [ ] Demo mode enabled and verified
- [ ] Voice barge-in behavior verified
- [ ] Failsafe text input flow verified
- [ ] Conversation history and restart behavior verified
- [ ] Mobile viewport sanity check complete

## Deployment Readiness

- [ ] .env and production env values configured
- [ ] API base URL points to production backend
- [ ] Health and metrics endpoints reachable in staging

## Release

- [ ] Create release commit
- [ ] Tag release: git tag v1.0
- [ ] Push tag: git push origin v1.0
- [ ] Archive release notes and architecture docs
