# Security policy

This repository is public. Do not submit credentials, confidential trading ideas,
proprietary algorithms, customer data or vulnerability exploit details in public
issues, PRs, Actions inputs, logs or artifacts.

## Reporting

Use GitHub's private vulnerability-reporting option under the Security tab **if
it is enabled**. Its availability must be verified in repository settings. If it
is unavailable, use an already established private channel with the repository
owner (`tltmgnt`) to arrange a secure report. No unverified email address or new
recipient is designated by this policy. Do not post a secret to request help.
The owner must enable private reporting or designate a verified private contact.

Include the affected commit, component, impact, and a minimal redacted reproduction.
Never include working API keys or private account data. If a credential was exposed,
revoke/rotate it at its provider; deleting a file or rewriting Git history does not
revoke a key or erase other people's copies.

## Supported scope

Security fixes target the current `main` branch. No response-time or certification
claim is made. Dependency scans and tests do not establish profitable trading or
complete security. The paper agent's order destinations and limits are enforced
by code; repository administrators remain capable of changing that code.

## Change review

`.github/CODEOWNERS` routes changes to the owner. It only becomes an approval gate
when required code-owner review is enabled in GitHub. Branch protection must also
require the CI checks, disallow force pushes/deletion, and constrain bypass access.
The private-core/public-interface boundary and remaining setup are documented in
[the IP boundary policy](docs/IP_BOUNDARY.md).
