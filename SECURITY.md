# Security and research data

Do not post credentials, private traces, raw provider responses, or exploitable details in public issues. Report security problems privately to the repository owner; GitHub private vulnerability reporting may be used when enabled for the repository.

TraceLab reads untrusted trajectory contents as data. It must not execute commands from imported tool calls, schema mappings, or model output on the host. Provider keys and standard Hugging Face credentials remain outside workspaces and Git. Classifier, segmentation, and intervention actions may send selected content to a configured model provider; schema assistance requires an explicit action.

Review dependency-update pull requests, IPC exposure, source URL handling, path access, cache identity, replay fidelity, and the handling of malformed/unbounded inputs. The repository policy checker catches common credential patterns and forbidden artifact paths but is not a comprehensive secret detector. If a credential is exposed, revoke or rotate it; deleting a file or commit alone is insufficient.

CI makes no paid model calls, receives no provider credentials, and publishes only generated application artifacts. The development macOS artifact is unsigned and unnotarized. Do not describe it as a signed production release.
