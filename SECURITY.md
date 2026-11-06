# Security policy

XOps Core is intended for **localhost-only** review. The web server binds only to `127.0.0.1` and includes per-process CSRF tokens. It has no sign-in feature and MUST NOT be reverse-proxied or exposed to public networks.

Never place real account tokens, private reports, original emails, paid datasets, or production SQLite files in a public repository. The program does not retrieve or verify the truth of source URLs; human review is mandatory.

Please report a potential security issue privately to repository maintainers via GitHub's private vulnerability reporting (if enabled), rather than opening a public issue with exploit details.
