# Security Policy

## System and Scope

Lumen Desktop is a Linux/KDE user-session application with local AI/tool execution, file handling, native helpers, embedded Server apps, and installation/update paths. Scope includes repository-owned code in `files/`, `bin/`, `native/`, packaging, installers, desktop integration, and build/release configuration.

Lumen Server, model providers, browser/build hosts, and upstream packages are external dependencies. Their client-facing boundaries and Lumen integration remain in scope; this policy is not an assessment of their separate implementations. Existing nested `SECURITY.md` files retain their local precedence.

## Threat Model and Trust Boundaries

Assets include user files and drafts, account/project data, device and provider credentials, Vault material, browser sessions, and authority to execute commands or change the system.

Attacker-controlled inputs include imported documents and archives, filenames and paths, project content, model/tool/MCP output, web/email content, links, notifications, and network responses. A configured Server is not automatically authorized to control the local computer. Loopback, a private network, or a project/build directory does not establish an authorization boundary or an OS sandbox.

## Security Invariants

- Local actions stay within the current OS user's authority and the owner's granted operation/resource scope. Connected actions additionally retain the correct Server origin, account, device, app and resource binding.
- Prompts, retrieved content, project guidance and model output cannot create consent or enlarge grants. Autonomous execution may use an existing owner-approved policy; content is not that policy.
- Browser control, capture, clipboard access, command execution and system changes retain their applicable local grants. Privilege-bearing IPC requests require an appropriate caller/authority check rather than trust in a local address alone.
- Device/provider secrets remain outside renderer JavaScript, URLs and unprotected logs. Embedded Server apps use only their intended scoped session; cross-app links transfer identifiers, not authority.
- Authenticated Server requests use verified HTTPS and authorized trust anchors. Redirects, app switches and external links cannot forward credentials to another origin or widen a native bridge's authority.
- Embedded web navigation, subframes, downloads and native actions enforce their own allowed scope. Untrusted previews and documents do not inherit privileged host access.
- Expiry, revocation, account/origin changes and replaced sessions invalidate affected app-managed displays and caches. Pending callbacks, retries and renewals cannot restore stale authority or duplicate unauthorized mutations.
- Imports, downloads, extraction and file operations validate paths and destinations, including symlinks and replacement races. They cannot overwrite or disclose unrelated files through attacker-controlled names.
- Parsers, image/document processing, network reads and subprocesses have appropriate size, time and resource limits; malformed input cannot escape its processing boundary.
- Vault sign-in and unlocking are separate permissions. Sensitive draft, clipboard, export and temporary-file handling respects the intended unlock scope and privacy choices.
- Updates and elevated installation remain bound to the configured source/channel, selected revision and approved privilege boundary. A checksum or installation marker alone is not evidence of publisher authenticity.

## Reportable Findings and Severity Context

Report reachable failures of these boundaries, including unauthorized execution or elevation, credential disclosure, cross-account/resource access, unsafe file writes, persistent compromise and material denial of service. State attacker control, required privileges/consent, affected entry point and concrete impact; assess severity from that evidence.

Prompt injection is security-relevant when lower-trust content causes an unauthorized action or disclosure. Intended execution of an owner-approved tool/plugin is not itself proof of a bypass. Private/beta distribution, localhost, Rust, passing tests or an upstream support policy do not by themselves make a reachable failure harmless.

## Out of Scope, Exclusions, and Accepted Risk

No Lumen-specific finding-class exclusions or accepted vulnerabilities are established by this policy. External implementation-only issues need assessment in their owning component; defects in Lumen's integration are not excluded. Unrecorded assumptions are not owner-approved risk acceptance.

## Known Limitations and Compensating Controls

Source guards and security-critical tests describe intended controls; they do not prove the installed configuration or every runtime path. Dynamic Server content and explicitly trusted executable extensions require their own assessment.

Legacy PDF cryptography in `native/document-core` is a document-format boundary, not evidence about protection of Lumen credentials. Already exported copies are not proven erasable by session revocation; app-managed cache isolation remains required.

Maintainers still need to define a private reporting channel and supported-version commitments. This policy supplies review context, not authorization to test accounts/devices, change data, disclose findings or publish code.
