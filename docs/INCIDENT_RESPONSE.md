# Incident Response

This runbook applies to availability, integrity, provider, privacy, credential, and security incidents. Use UTC in the incident record and preserve the affected users' Bangla/English communication needs.

## Roles

| Role                  | Responsibility                                                                     |
| --------------------- | ---------------------------------------------------------------------------------- |
| Incident commander    | Owns severity, priorities, decisions, handoffs, and closure                        |
| Operations lead       | Platform containment, rollback, recovery, and evidence                             |
| Engineering lead      | Technical diagnosis, safe fix, validation, and follow-up                           |
| Security/privacy lead | Credential containment, forensic preservation, breach assessment, legal escalation |
| Communications lead   | Internal updates, status page, customer/provider messaging                         |
| Scribe                | UTC timeline, hypotheses, commands/changes, evidence links, approvals              |

The restricted on-call directory contains current people, phone numbers, platform owners, provider escalation paths, legal counsel, and regulator/insurer contacts. Test access quarterly.

## Severity

- **SEV-1:** confirmed or suspected unauthorized access, secret compromise, data loss/corruption, broad checkout/auth outage, duplicate financial effects, or privacy/safety impact.
- **SEV-2:** sustained SLO breach, worker/provider outage, growing unknown/reconciliation/dead-letter backlog, or material partial outage.
- **SEV-3:** contained degradation with a workaround and no evidence of data/security impact.
- **SEV-4:** informational event or low-risk defect handled through normal change management.

When uncertain, declare the higher severity. SEV-1 acknowledgement target is five minutes; SEV-2 is fifteen minutes.

## First 15 Minutes

1. Open the incident channel/record, assign incident commander and scribe, record detection time and current release SHA.
2. State known impact, unknowns, affected environments/components, and next update time. Do not speculate about cause or breach scope.
3. Preserve request IDs, safe logs, deployment/config audit history, provider references, and platform events. Do not copy raw secrets or PII into chat.
4. Stop deployments and risky retries. Disable affected optional providers/features through audited kill switches where this reduces harm.
5. For credential suspicion, revoke/rotate the credential first, invalidate affected sessions/tokens, then investigate. Do not wait for complete attribution.
6. For financial/provider ambiguity, freeze blind retries and reconcile authoritative external state.
7. Page security/privacy immediately for any possible unauthorized access, data exposure, deletion failure, or backup compromise.

## Containment

Choose the smallest reversible action that prevents further harm:

- Roll Vercel, Railway web, and worker together only when schema compatibility is confirmed.
- Disable one provider or capability rather than weakening signature/authentication checks.
- Restrict traffic or put an affected mutation behind a maintenance response while preserving read-only status information.
- Revoke leaked provider/API/database credentials and issue new versions through the secret manager.
- Revoke customer/admin refresh sessions when token material or auth integrity may be affected.
- Isolate a suspect database/backup clone; never investigate by modifying the only copy.
- Preserve compromised resources until security approves destruction and evidence requirements are met.

Never disable audit logs, CSRF, webhook verification, idempotency, encryption, readiness dependencies, or PII redaction to restore service.

## Diagnosis And Eradication

1. Build an evidence-backed timeline from request IDs, deployment/config changes, audit events, provider records, and platform logs.
2. Separate symptom, trigger, contributing conditions, and root cause. Maintain competing hypotheses until disproved.
3. Determine the earliest possible access/failure time and affected data/resources.
4. Patch through review and normal CI where time permits. Emergency changes still require a second reviewer and immutable SHA.
5. Rotate all material that could be derived or reached from a compromised credential; do not rotate only the first observed token.
6. Scan history/artifacts for secret exposure and invalidate the secret before rewriting any history. Git history changes require repository-owner approval and user coordination.

## Recovery

1. Select rollback, forward fix, provider disable, or data recovery using `docs/DEPLOYMENT.md` and `docs/BACKUP_RESTORE.md`.
2. For a restore, keep the candidate isolated, validate integrity, replay deletion/suppression/consent/credential revocation after the recovery point, and obtain incident-commander plus data-owner approval before cutover.
3. Run release preflight, public smoke, authenticated canary, worker heartbeat, backlog, reconciliation, and monitoring checks.
4. Restore traffic gradually. Keep provider kill switches available and watch duplicate/unknown outcomes.
5. Continue elevated monitoring for at least one hour after SEV-1/SEV-2 stability, or longer when provider settlement/data integrity is delayed.

## Privacy And Breach Assessment

Security/privacy lead records:

- Data categories, approximate subjects/records, sensitivity, encryption state, geography, and affected processors.
- Whether confidentiality, integrity, availability, deletion, consent, or suppression was violated.
- Likely consequences and mitigations already applied.
- Legal/contractual notification deadlines for Bangladesh and any other applicable jurisdiction.
- Provider, insurer, regulator, law-enforcement, and data-subject notification decisions with counsel approval.

Do not promise that no data was accessed until evidence supports it. Preserve a legally reviewed copy of notices and recipient criteria. Customer messaging must be understandable in Bangla and English, state protective steps, and avoid exposing other users.

## Communications

| Audience             | Content                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------ |
| Internal responders  | Facts, impact, safe evidence links, decisions, owner, next update                          |
| Leadership/support   | Customer/business impact, workaround, approved wording, next update                        |
| Public status        | Affected capability and observed impact; no exploit detail, PII, blame, or unsupported ETA |
| Providers            | Stable references and sanitized evidence through approved support channel                  |
| Customers/regulators | Legal/privacy-approved scope, actions, risks, and contact path                             |

SEV-1 updates occur at least every 15 minutes and SEV-2 every 30 minutes until stable. Silence is replaced by “investigation continues; no material change” with the next update time.

## Evidence Handling

- Store incident artifacts in the restricted incident repository with least-privilege access and retention from `docs/PRIVACY_RETENTION.md`.
- Hash exported evidence, record collector/time/source, and preserve an immutable original.
- Redact routine working copies. Raw PII/provider payload access requires security approval and an access log.
- Never upload production data, database dumps, browser storage, credentials, or raw payloads to public issue trackers or CI artifacts.
- Legal hold overrides normal deletion only with documented legal approval, scope, owner, and review date.

## Closure And Postmortem

An incident closes only when impact has stopped, data/provider state is reconciled, alerts and SLOs are stable, credentials are rotated where needed, customer/legal actions are assigned, and follow-up owners/dates are accepted.

SEV-1/SEV-2 requires a blameless postmortem within five business days containing:

- Summary, impact, duration, detection, response, and recovery.
- UTC timeline and evidence links.
- Root cause and contributing technical/process conditions.
- What worked, what failed, and where detection/response was slow.
- Corrective actions classified as prevent, detect, contain, recover, and learn.
- Named owner, due date, priority, verification method, and closure evidence for every action.
- SLO/error-budget effect and decision on release freeze or capacity reduction.

Run a tabletop before launch and at least twice yearly. Rotate scenarios among database corruption/PITR, leaked provider credential, malicious admin/session theft, payment webhook ambiguity, worker/dead-letter outage, Cloudinary loss, and privacy deletion failure.
