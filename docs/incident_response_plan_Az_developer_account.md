# Incident Response Plan — Goodsense Trading India Private Limited

**Version:** 1.0  
**Effective Date:** May 2026  
**Next Review Date:** November 2026  
**Owner:** Himanshu Dhiman (Director)

---

## 1. Scope

This plan covers security incidents involving data accessed via Amazon Selling Partner API (SP-API), including order data, financial/settlement data, and account information stored in our internal systems.

---

## 2. Defined Roles

| Role | Person | Responsibility |
|------|--------|----------------|
| Incident Owner | Himanshu Dhiman | Detect, respond, notify, and document all incidents |
| Secondary Contact | Shubhra (Co-founder) | Backup if Himanshu is unreachable |

As a 2-person organization, Himanshu Dhiman is the sole person responsible for identifying, responding to, and reporting security incidents.

---

## 3. What Constitutes a Security Incident

- Unauthorized access to Amazon SP-API credentials (client ID, client secret, refresh token)
- Leaked credentials in a public repository, shared document, or email
- Unauthorized access to our internal database (Supabase) containing Amazon order/payout data
- Compromise of any system that stores or processes Amazon buyer or transaction data
- Loss or theft of a device that has access to Amazon Seller Central or our internal systems

---

## 4. Incident Response Procedure

### Step 1 — Detect (within hours of discovery)
- Monitor for unusual API activity, failed login alerts, or GitHub secret scanning alerts
- If a breach is suspected, treat it as confirmed until proven otherwise

### Step 2 — Contain (immediately)
- Revoke compromised SP-API credentials via Amazon Developer Console
- Rotate all related secrets (client secret, refresh token, AWS IAM keys)
- Remove any exposed credentials from public repositories
- Revoke database access keys if the Supabase instance is implicated

### Step 3 — Notify Amazon (within 24 hours of detection)
- Email **security@amazon.com** with:
  - Nature of the incident
  - Data potentially exposed (order data, financial data, buyer PII if applicable)
  - Steps taken to contain the breach
  - Timeline of discovery and response

### Step 4 — Document
- Record the incident in writing: what happened, when, how it was discovered, what was affected, what was done
- Store record in `docs/incident_log/` (create folder if needed)

### Step 5 — Remediate
- Identify root cause
- Fix the vulnerability (e.g., move credentials to environment variables, enable MFA, rotate all keys)
- Verify no residual exposure

---

## 5. Security Controls in Place

- SP-API credentials stored in `.env` files — gitignored, never committed to version control
- GitHub repository is private
- Supabase database accessed via secret keys stored in environment variables only
- Amazon Seller Central access protected by MFA

---

## 6. 6-Month Review Schedule

| Review Date | Reviewer | Notes |
|-------------|----------|-------|
| November 2026 | Himanshu Dhiman | First scheduled review |
| May 2027 | Himanshu Dhiman | — |

At each review: verify credentials have been rotated, confirm no credentials are hardcoded, update this document if roles or systems have changed.

---

## 7. Contact

**Amazon Security:** security@amazon.com  
**Internal Owner:** himanshu1858@gmail.com
