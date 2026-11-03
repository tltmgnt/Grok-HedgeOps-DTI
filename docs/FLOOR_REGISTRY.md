# Phase 25 — Local recovery floor registry

`publish_recovery_floor(store, checkpoint, directory, floor_key)`
authenticates a new journal floor and publishes it as a numbered, owner-only
JSON record in an existing operator-controlled directory. It checks that the
checkpoint matches the live journal, that the new floor strictly advances
the last floor, and that the journal still contains the prior floor's head.

`latest_recovery_floor(directory, floor_key)` validates the complete
locally available record chain and every floor HMAC before returning the
highest recorded floor. Use the result as `trusted_floor` in
`verify_restored_journal(..., trusted_floor=floor, floor_key=floor_key)`.

The implementation uses POSIX `flock` for cooperating writers, exclusive
file creation, file sync and directory sync. It does not automatically
create the registry directory or distribute the authentication key.

**Trust limitation:** this is a *local operational registry*, not an
independent monotonic authority. Deleting a suffix of valid records can
make an older floor appear latest; an attacker with the key can forge
records. Place the registry under independently administered, immutable or
externally monitored storage, and retain an independent record of the
latest sequence/hash. Filesystem permissions alone do not prevent
privileged rollback. No remote publishing API or trusted timestamp is
provided.

Run `python release_check.py --verbose` and verify both CI jobs.
