# Final migration and rollback

## Migration

Author-domain migration remains idempotent and non-destructive:

1. Back up the per-novel data directory.
2. Start the new runtime once; it creates or validates StoryBible,
   CanonicalState, StoryThread, Memory and generation-mode files.
3. Legacy Tick, fact-ledger, memory and summary files remain in place and are
   read only as lower-authority migration inputs.
4. Confirm the UI evidence ledger shows the expected Bible/Canonical revisions
   and that manuscript export contains committed sections only.
5. Run the Recorded smoke and unified final acceptance before enabling real
   Author traffic.

Never place provider credentials in `config.json`; keep them in `.env` or a
process-only provider file.

## Rollback

Rollback is deployment-level and preserves data:

1. Stop writers and retain the complete novel data directory and
   `generation_transactions/` journal.
2. Deploy the previously known-good commit or image on a separate branch; do
   not merge this final-goal branch into main as part of rollback.
3. Keep the new Author-domain files. Older code may ignore them; do not delete
   or rewrite them.
4. If the previous runtime cannot read a post-migration novel, restore the
   backed-up directory to a new location and point the previous deployment at
   that copy.
5. Re-enable writes only after its health checks and a committed-only export
   comparison pass.

The final P6 checkpoints are diagnostic evidence. Because the repair-round
allowance is exhausted, rollback or resume does not authorize another real P6
attempt.
