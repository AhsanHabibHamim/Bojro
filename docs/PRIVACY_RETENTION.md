# Privacy And Retention

Policy owner: privacy/legal. Technical owner: security and platform engineering. Last technical review: 2026-11-08.

This schedule is the operational target, not legal advice. Legal must approve it against Bangladesh law, tax/accounting requirements, provider contracts, and the published privacy notice before go-live. Where automated enforcement is not implemented, the launch checklist requires a tested manual control with an owner and deadline; silent indefinite retention is not acceptable.

## Principles

- Collect the minimum data required for commerce, security, consent, support, and legal obligations.
- Define purpose, owner, access, retention trigger, deletion/anonymization, and processor for every data class.
- PostgreSQL is the authoritative personal-data store. Redis is transient and non-authoritative.
- Do not put PII in logs, metrics labels, URLs/query strings, analytics, CI artifacts, issue trackers, or routine incident chat.
- Consent is specific, versioned, revocable, and separate from service-required processing.
- Deletion does not erase records that must be retained for a documented legal purpose; those records are minimized, access-restricted, and no longer used for marketing/product personalization.
- Backups are immutable until expiry. A restore must replay post-backup deletion, suppression, consent withdrawal, disable, and revocation events before production use.

## Retention Schedule

| Data class                              | Purpose                                         | Retention target                                                                                  | End-of-life action                                                                 | Enforcement status                                                        |
| --------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Guest identity and abandoned guest cart | Session/cart continuity                         | 30 days after last activity                                                                       | Delete or irreversibly unlink                                                      | Application expiry plus periodic verification required                    |
| Customer account/profile                | Account service                                 | Active account; 30-day recovery window after approved deletion request                            | Delete non-required fields; retain anonymized linkage only where required          | Deletion workflow/evidence required before launch                         |
| Addresses                               | Fulfillment convenience                         | Until user deletes or account deletion; unused deleted values leave active tables immediately     | Hard delete unless snapshotted on a retained order                                 | API deletion exists; purge verification required                          |
| Order/item/address/contact snapshots    | Contract, fulfillment, tax/accounting, disputes | 7 years after order completion/cancellation, subject to legal approval                            | Anonymize fields not legally required, then delete at expiry                       | Policy/manual until approved retention job exists                         |
| Payment/refund/settlement records       | Financial reconciliation and fraud              | 7 years after final settlement, subject to legal approval                                         | Delete raw payloads earlier; retain minimal financial ledger until expiry          | Policy/manual; provider payload rule below                                |
| Shipment/tracking records               | Fulfillment and disputes                        | 2 years after delivery/cancellation unless linked financial evidence requires longer              | Delete tracking details; retain minimal order event if required                    | Policy/manual                                                             |
| Provider webhook/raw payload            | Verification, replay, dispute diagnosis         | 90 days after terminal processing; up to 1 year only for an open dispute                          | Delete payload; retain non-PII digest/event identity and result                    | Retention job/evidence required                                           |
| Idempotency results                     | Safe command replay                             | Until the persisted endpoint-specific `expires_at`                                                | Delete in bounded batches                                                          | Automated daily transient cleanup implemented; monitor oldest expired row |
| Support tickets/messages                | Customer support and disputes                   | 2 years after closure; longer only under legal hold                                               | Delete/anonymize PII and attachments                                               | Policy/manual                                                             |
| Reviews and review media                | Published user content/moderation               | Until user deletes/account deletion or moderation/legal need ends                                 | Remove public content; delete owned media; retain minimal moderation audit 2 years | API/media cleanup exists; account-deletion linkage must be verified       |
| Wishlist/preferences                    | User convenience                                | Until user clears/account deletion                                                                | Delete                                                                             | API deletion plus account-deletion verification required                  |
| Admin audit events                      | Security, fraud, privileged accountability      | 7 years, subject to legal/security approval                                                       | Delete at expiry; never rewrite event content                                      | Append-only implemented; expiry control required                          |
| Security/application logs               | Reliability and security                        | 30 days searchable, up to 90 days restricted archive                                              | Delete                                                                             | Configure in Vercel/Railway/error tracker                                 |
| Incident evidence                       | Security/legal investigation                    | 2 years after closure or legal-hold end                                                           | Secure deletion                                                                    | Restricted incident repository control                                    |
| Consent events                          | Proof of consent/withdrawal                     | 7 years after the relevant relationship/event, subject to legal approval                          | Delete or retain anonymized proof if legally allowed                               | Append-only evidence implemented; expiry control required                 |
| Newsletter pending confirmation         | Double opt-in                                   | 7 days                                                                                            | Expire token and delete unnecessary encrypted address data                         | Automated expiry implemented; verify job                                  |
| Newsletter subscribed/suppressed        | Delivery and opt-out compliance                 | While subscribed; suppression proof retained 7 years after unsubscribe, subject to legal approval | Erase encrypted delivery fields; retain minimal keyed suppression proof            | Suppression exists; terminal erasure/expiry verification required         |
| Notification encrypted content          | Delivery retries/support                        | 30 days maximum                                                                                   | Cryptographic/content erasure                                                      | Automated setting `NOTIFICATION_CONTENT_RETENTION_DAYS=30`                |
| Notification attempt metadata           | Reliability/audit                               | 180 days                                                                                          | Delete                                                                             | Automated setting `NOTIFICATION_ATTEMPT_RETENTION_DAYS=180`               |
| Analytics events                        | Consent-based measurement                       | 90 days maximum                                                                                   | Delete identifiers/event rows                                                      | Automated setting `ANALYTICS_EVENT_RETENTION_DAYS=90`                     |
| Assistant sessions/messages             | Disclosed support assistant                     | 30 days maximum                                                                                   | Delete encrypted transcript and grants                                             | Automated setting `ASSISTANT_RETENTION_DAYS=30`                           |
| OTP challenge/recipient state           | Authentication                                  | Challenge TTL, normally 5 minutes                                                                 | Redis expiry; terminal ciphertext erasure                                          | TTL/terminal erasure implemented                                          |
| Rate-limit/cache/worker heartbeat data  | Security/performance                            | Minutes to bounded cache TTL                                                                      | Redis expiry/eviction                                                              | Redis TTL; non-authoritative                                              |
| Cloudinary original customer media      | Review/content rendering                        | Same as owning review/media record                                                                | Provider deletion with retry and reconciliation                                    | Cleanup worker exists; backup/version expiry must match policy            |
| Database backups/PITR                   | Disaster recovery                               | PITR >=7 days; daily logical backups 30 days; monthly drill evidence 1 year                       | Provider/object lifecycle deletion                                                 | External configuration/evidence required                                  |

If legal approves a different period, update this file, the public notice, worker settings/jobs, backup lifecycle, and launch evidence in one reviewed change.

## Access And Processing

- Customer data access is role- and task-limited. Support sees only the minimum customer-safe view; internal notes and provider payloads remain restricted.
- Production database consoles, backup restores, Cloudinary originals, raw webhook payloads, and encryption keyrings require time-bounded operator access and an audit record.
- Admin export/CSV/PDF artifacts are stored only for the active task and securely deleted; they are not attached to public tickets.
- Processors and sub-processors must be listed in the public privacy notice with purpose, data category, region where known, contract/DPA status, retention, and deletion path.
- Provider credentials and encryption keys are not personal data backups and use the separate secret-manager lifecycle.

## Data-Subject Request Runbook

1. Receive requests only through the approved privacy channel and create a restricted case ID.
2. Verify identity proportionately without collecting reusable excessive documents. Never ask for passwords, OTPs, or full payment credentials.
3. Search by normalized keyed identities through approved tooling; do not distribute raw database dumps.
4. Classify access, correction, portability, deletion, objection/withdrawal, and marketing opt-out. Record jurisdictional deadline and owner.
5. Export only the subject's customer-visible data in a safe format; exclude other users, internal security signals, secrets, and privileged notes.
6. For deletion, immediately withdraw optional consent, unsubscribe/suppress marketing, revoke sessions, disable login, and stop new processing.
7. Delete/anonymize eligible account, address, wishlist, support, review/media, analytics, assistant, and engagement data. Restrict legally retained commerce/audit records to their documented purpose.
8. Record every system/processor action and exception. Obtain a second-person review before completion.
9. Confirm completion in Bangla or English as requested without exposing retained sensitive detail.
10. Allow immutable backups to expire normally; place the case in the deletion replay ledger used by any restore.

No data-subject request is completed based only on frontend disappearance.

## Consent And Marketing

- Necessary commerce/auth processing does not depend on optional analytics or advertising consent.
- GA4 requires analytics consent. Pixel and Meta CAPI require advertising consent. Consent defaults denied.
- Marketing email/SMS/cart reminders require the appropriate current opt-in and verified recipient. Recheck immediately before dispatch.
- Unsubscribe and consent withdrawal take effect immediately for future optional sends; suppression prevents re-import/re-subscription without a new valid flow.
- Purchase and fulfillment messages are transactional and still honor channel validity, security, and minimization.
- WhatsApp handoff sends no assistant transcript, phone/order value, or customer data in the URL/message.

## Backup And Restore Privacy

Follow [BACKUP_RESTORE.md](BACKUP_RESTORE.md). Backup access is an audited privileged event. A recovery environment has no outbound provider connectivity, uses isolated credentials, and is destroyed after validation.

Before restored data can serve traffic:

1. Replay account deletion and disable events after the recovery timestamp.
2. Replay newsletter suppression/unsubscribe and consent withdrawal.
3. Replay credential/session/provider-token revocations.
4. Run retention cleanup through the current time.
5. Reconcile Cloudinary deletion state.
6. Obtain privacy/data-owner sign-off.

## Legal Hold

A legal hold records authority, scope, data classes, custodian, start date, review date, and access list. It suspends only the affected deletion, not security controls or unrelated retention. Review holds at least quarterly and delete held data promptly when released.

## Evidence

Quarterly privacy evidence includes retention-job success, oldest-row samples by data class, processor deletion results, backup lifecycle, restore replay drill, access review, data-subject request timeliness, consent/opt-out tests, and unresolved exceptions. Evidence contains counts and timestamps, not raw PII.
