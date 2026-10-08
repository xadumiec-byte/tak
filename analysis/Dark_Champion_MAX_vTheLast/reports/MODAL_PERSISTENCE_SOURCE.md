Verified 2026-10-07 for the current production persistence question.

Official sources:
- https://modal.com/docs/guide/sandbox-files
- https://modal.com/docs/guide/sandboxes
- https://modal.com/docs/guide/volumes

Sandboxes accept Modal Volumes via volumes mount mapping. VM runtime supports Docker with a real Linux kernel; GPU sandboxes use gVisor. Volumes persist through background commits and final termination commit; v2 permits explicit sync on the mountpoint. Single-writer ownership is necessary: simultaneous writes to the same file have last-write-wins behavior. Runtime database mmap/fsync behavior and restart durability on mounted volumes still require actual tests. No database persistence PASS inferred from documentation.


Redis crash recovery recorded 2026-10-08 on the production Modal state Volume:
- Redis 7.4.11 rejected the 163,822-byte incremental AOF at its first invalid record (only 494 bytes valid).
- A full pre-repair copy remains at `/state/redis-recovery-backup-20261008T0117/`; its AOF SHA-256 is `82a7ce5f810906aaef4108481184549cffd61010ad82e80681c4c58402a08b44`.
- Redis's own AOF checker validated the 494-byte recovered prefix. Redis 7.4.11 started from that state and survived a SIGKILL/restart test; the canonical live `redis_crash_recovery` gate also PASSed.
- The corrupted suffix was not guessed or applied. It is preserved only in the backup for future forensic recovery.
