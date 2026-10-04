# Engine qualification — not a password manager

Run `python research/vault/probe_keepassxc.py` with a separately installed,
distribution-verified `keepassxc-cli`. No runtime dependency is added to Lumen.
The probe accepts no input files or credentials. It uses fixed public synthetic
secrets, private temporary directories, and an inherited anonymous memory fd for
XML. It prints facts only, and deletes its synthetic encrypted files afterward.

Observed with **KeePassXC CLI 2.7.12**, distribution package **2.7.12-5.1**:

| Check | Result |
|---|---|
| `db-create -p -t 1000` | KDBX 3.1, AES-KDF |
| Export and import using memory fd | Worked; output KDBX 3.1, AES-KDF |
| Wrong password | Rejected |
| Corrupted ciphertext | Rejected |
| Truncated file | Rejected |
| Argon2id selection via supported CLI option | Not available |
| Engine production qualification | **Not passed** |

This only probes a specific CLI pathway; it is not a finding that KeePassXC lacks
Argon2id support in its own application. Full field/history compatibility,
resource limits, lock races, durable conflict-safe writes, process isolation,
license suitability and independent review remain open.

Sources: upstream [CLI manual](https://github.com/keepassxreboot/keepassxc/blob/2.7.12/docs/man/keepassxc-cli.1.adoc),
[Import](https://github.com/keepassxreboot/keepassxc/blob/2.7.12/src/cli/Import.cpp),
[DatabaseCreate](https://github.com/keepassxreboot/keepassxc/blob/2.7.12/src/cli/DatabaseCreate.cpp),
[KDBX specification](https://keepass.info/help/kb/kdbx.html).
No upstream engine code is copied or linked into Lumen. The CLI's license does
not become an assertion that Lumen's eventual integration is legally cleared.

Do not connect the Python/QML design prototype to real secrets. The native
secure-input/broker boundary in the approved spec is still a separate deliverable.
