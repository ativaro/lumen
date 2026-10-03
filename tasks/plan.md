# Localization, visible installation and licensing review

1. Establish the shared German/English translation API and catalog validation.
2. In parallel, update separate main/Files UI, companion-tool and settings/panel
   source groups using that contract; keep data and command identifiers stable.
3. Add remaining shared status/backend text and language preference behavior.
4. Run catalog/static checks, German regression tests and native English checks;
   inspect rendered interfaces, package and install the user bundle.
5. Move installation to the README opening, document verified access constraints,
   explain licensing choices, and apply only an explicitly selected license plan.
6. Review distributable files, commit and push, verify remote main and private docs.

# Interoperability (user-approved 2026-10-03)

Implement the numbered cross-app scenarios in vertical slices, following docs/interop/CONTRACT.md. Shared references/dispatch precede independent source/destination, backup, and audio work. Integrate each completed path into native menus, test against temporary stores, then verify cold/warm launch and update the installed user runtime. Track exact requirement evidence in docs/interop/COVERAGE.md, rather than counting generic actions as finished workflows.
