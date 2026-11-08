# Publication boundary and proprietary IP

## Verified scope

This repository is public and its existing LICENSE is Apache-2.0. Its existing
published source remains visible and subject to the applicable license. Contributor
attribution is not a grant of administrator access or a transfer of underlying
copyright ownership. Dependency maintenance controls protect software integrity;
they do not make source confidential.

The original **Ω-R3B Repository Transformation** specification has not been supplied
or identified in the inspected repository. These controls must not be represented
as a verified implementation of that named transformation.

## Controls shipped in this repository

- `.github/CODEOWNERS` identifies `@tltmgnt` for all source, workflow, dependency,
  security-policy and license changes, including CODEOWNERS itself.
- The `public-boundary` CI check rejects prohibited tracked paths, private-key
  files, common credential patterns and tracked symlinks. It never prints matched
  values. The standalone `--history` option also scans unique reachable Git blobs.
- `.gitignore` reduces accidental staging of local environments, private material,
  key files, databases and model-weight artifacts. Ignore rules do not protect
  already tracked files; the CI check handles tracked paths.
- Action SHAs, dependency hash locks, tests and dependency/security audits remain.
- `SECURITY.md` establishes a reporting policy without claiming a reporting feature
  is enabled or inventing a security contact.

These controls do not detect all proprietary information or every secret format.
They cannot prevent an administrator from changing checks, using bypass privileges,
or publishing a new artifact. They are not encryption or a legal ownership opinion.

## Private core architecture

Confidential algorithms, model weights, research data, internal prompts, secrets,
production execution adapters and customer information must be held outside this
public repository in an access-controlled private repository or service. A directory
named `private/` inside a public repository is not private.

The public side should contain only deliberately publishable interfaces, schemas,
synthetic examples, redacted tests and documentation. A private service should enforce
its own authentication, authorization and rate limits, return only approved outputs,
and never expose implementation details or credentials through errors or logs.

**Migration is not complete.** No existing code has been silently reclassified,
removed, moved to a newly licensed repository, or claimed confidential. Before a
private-core migration, the owner must identify the exact files/algorithms/data to
protect and approve the destination and interface. Existing public/licensed versions
and other people's copies cannot be made secret retroactively.

## GitHub administration still required

The code connector cannot administer branch protection or repository security
settings. Verify and apply the following as an authenticated owner:

1. Protect `main`, require PRs and passing checks for `unit-tests (3.10)`,
   `unit-tests (3.12)`, `unit-tests (3.13)`, `runtime-lock`, `dependency-audit`,
   `bandit`, and `public-boundary`. Require branches to be up to date.
2. Require code-owner review; dismiss stale approvals and resolve conversations.
   Do not grant bots a review bypass. Audit administrator bypass explicitly.
3. Disallow force pushes and branch deletion. Review collaborator and installed-App
   permissions separately: a bot can act through an App without being a collaborator.
4. Enable and verify available native secret scanning, push protection, Dependabot
   alerts/security updates and private vulnerability reporting. Availability varies
   by account/repository plan; a documentation file does not enable these features.
5. Restrict broker environments to `main` and appropriately scoped credentials;
   review who can approve deployments and who can modify workflow files.

A sole maintainer cannot approve their own PR. Before requiring an independent
approval for every owner-authored PR, designate a trusted second reviewer or choose
and document an owner-only emergency/bypass process. Do not add another account or
broaden App permissions simply to make a check pass.

## Exposure audit and incidents

Run locally from a checkout with full history:

```sh
python scripts/check_public_boundary.py --history
```

This reports rule names, paths, line numbers and blob IDs, never matched values.
A clean result only covers the implemented patterns. Review account permissions,
public Actions inputs/logs/artifacts, releases and other external copies separately.
Model critique text and user-entered trade hypotheses can be sensitive even if they
contain no recognizable credential. Do not submit them through public workflows.

If sensitive material was published, inventory the exposure, rotate affected keys,
review lawful remediation and licensing with appropriate counsel, and preserve an
incident record privately. Visibility or license changes require an explicit owner
decision; neither is an erasure mechanism.
