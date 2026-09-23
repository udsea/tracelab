# Security and research data

Do not post credentials, private traces, raw provider responses, or exploitable details in public issues. Report security problems privately to the repository owner; GitHub private vulnerability reporting may be used when enabled for the repository.

TraceLab reads untrusted trajectory contents as data. It must not execute commands from imported tool calls, schema mappings, or model output on the host. Provider keys and standard Hugging Face credentials remain outside workspaces and Git. Classifier, segmentation, and intervention actions may send selected content to a configured model provider; schema assistance requires an explicit action.

Review dependency-update pull requests, IPC exposure, source URL handling, path access, cache identity, replay fidelity, and the handling of malformed/unbounded inputs. The repository policy checker catches common credential patterns and forbidden artifact paths but is not a comprehensive secret detector. If a credential is exposed, revoke or rotate it; deleting a file or commit alone is insufficient.

CI makes no paid model calls, receives no provider credentials, and publishes only generated application artifacts. The development macOS artifact is unsigned and unnotarized. Do not describe it as a signed production release.

## Tracked upstream advisory

The lockfile contains `glib` 0.18.5 through Tauri 2's Linux/BSD GTK 0.18 dependencies. [GHSA-wrw7-89jp-8q8g](https://github.com/advisories/GHSA-wrw7-89jp-8q8g) affects this version; its first patched line is 0.20, outside GTK's compatible dependency range. `cargo tree --locked --target aarch64-apple-darwin --invert glib` confirms it is absent from the shipped macOS ARM64 dependency graph. Keep the alert open and resolve the upstream GTK dependency before introducing Linux/BSD distribution. Do not force an incompatible dependency override or dismiss this as fixed. This platform-specific finding does not establish a general security audit of the app.

The Vitest / `@vitest/mocker` redirect-mock advisory is addressed by updating the development test tool and lockfile to Vitest 4.1.11.
