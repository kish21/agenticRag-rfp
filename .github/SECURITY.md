# Security Policy

We take the security of the Meridian AI Platform seriously. This document explains
how to report a vulnerability and what to expect when you do.

## Supported Versions

The platform is pre-1.0 and ships from `master`. Security fixes are applied to the
latest `master` only. Tagged releases will be listed here once they exist.

| Version  | Supported |
| -------- | --------- |
| `master` | ✅        |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report privately via either channel:

- **GitHub** — use the **"Report a vulnerability"** button under the repository's
  **Security** tab (GitHub Private Vulnerability Reporting).
- **Email** — `kishorekv2@gmail.com` with the subject line `SECURITY:` followed by a
  short description.

Please include, where possible:

- The component affected (agent, API route, retrieval, storage, auth, etc.).
- Steps to reproduce, or a proof-of-concept.
- The impact you believe it has (data exposure, tenant cross-access, RCE, etc.).
- Any suggested remediation.

## What to Expect

| Stage                  | Target                          |
| ---------------------- | ------------------------------- |
| Acknowledgement        | within 3 business days          |
| Initial assessment     | within 7 business days          |
| Fix or mitigation plan | communicated after triage       |

We will keep you informed of progress and let you know when the issue is resolved.
We support coordinated disclosure: please give us a reasonable window to ship a fix
before any public write-up.

## Scope

In scope: the application code in this repository — agent pipeline, FastAPI services,
retrieval/storage layers, authentication, and tenant isolation.

Out of scope: third-party services and dependencies (report those upstream), and
findings that require physical access or a compromised host.

## Recognition

We are grateful to researchers who report responsibly. With your permission we are
happy to credit you once a fix has shipped.
