# Project governance

DeployGuard AI is maintained as an open-source project with a small-core, evidence-first review model. The goal is to keep the product useful for real operations without weakening its safety boundaries.

## Roles

- **Maintainers** are responsible for the roadmap, releases, security response, and final merge decisions. The current repository maintainer is [@kingggg5](https://github.com/kingggg5).
- **Contributors** propose changes, maintain integrations, improve documentation, and participate in review.
- **Reviewers** are trusted contributors who provide technical, product, security, or accessibility review. Review authority is granted by maintainers and can be withdrawn when project needs change.

## Decision making

Maintainers seek consensus in issues and pull requests. When consensus is not possible, the maintainer responsible for the affected area makes the decision and documents the rationale. Security, privacy, data-model, and API compatibility decisions should include a written trade-off and a test or migration plan.

Changes that affect these boundaries require explicit maintainer review:

- authentication, authorization, secrets, tenant isolation, or audit retention;
- risk-scoring weights, evidence contracts, or synthetic/connected data labeling;
- deployment, rollback, shell execution, cluster credentials, or autonomous remediation;
- public API compatibility, database migrations, or connector permission scopes.

## Releases

Releases are cut from main after required checks pass. Release notes should describe user-visible changes, migrations, security fixes, known limitations, and any compatibility impact. Breaking API or schema changes require a migration path and a documented rollback strategy before release.

## Becoming a maintainer

Maintainers may invite contributors who demonstrate sustained, high-quality contributions, thoughtful review, and respect for the Code of Conduct. New maintainers receive the least privilege needed for their responsibilities. Maintainer changes are announced in the repository and recorded in this document.

## Changes to this policy

Open a pull request with the proposed change and its rationale. Policy changes require maintainer approval and should not be bundled with unrelated product work.

## ภาษาไทย

โปรเจกต์ใช้รูปแบบดูแลแบบ maintainer-led โดยยึดหลัก evidence-first ความปลอดภัย และ backward compatibility เป็นหลัก การเปลี่ยนแปลงที่กระทบสิทธิ์, secret, tenant isolation, scoring, API, database migration หรือ autonomous remediation ต้องมีการ review และแผนทดสอบที่ชัดเจน
