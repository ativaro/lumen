# Lumen interoperability

Implement the user-approved 100-example proposal plus Wissen-to-Vault and Files-to-Reader. The shared boundary and module map live in docs/interop/CONTRACT.md; numbered acceptance evidence lives in docs/interop/COVERAGE.md. Preserve native desktop interaction, DE/EN naming with Lumen prefix, explicit side effects, local ownership and source backlinks.

Commands: `QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de /usr/bin/python3 -m unittest discover -s files -v`; native cold/warm launch checks under tests/. Python modules and tests stay in files/, launchers in bin/, desktop handlers in data/applications/. Follow existing Library/Job/QSettings patterns; interface helpers are isolated from the already large app.py.

Build order: reference and transport contract → Files/Reader and Wissen/Vault vertical flows → destination adapters → selected source actions → cross-app relations/search → backup/restore and audio → native integration/local installation. Changes are additive; original files and uncommitted unrelated README changes are preserved. Never silently send mail, enable audio automation or make model calls. Existing persistence APIs keep their authority; link/copy modes have distinct behavior.
