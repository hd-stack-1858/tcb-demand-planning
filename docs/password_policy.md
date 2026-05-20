# Password and Authentication Policy — Goodsense Trading India Private Limited

**Version:** 1.0  
**Effective Date:** May 2026  
**Next Review Date:** May 2027  
**Owner:** Himanshu Dhiman (Director)

---

## 1. Scope

This policy applies to all accounts and systems used by Goodsense Trading India Private Limited, including Amazon Seller Central, Supabase, GitHub, and any system that stores or processes Amazon SP-API credentials or buyer/transaction data.

---

## 2. Password Requirements

- **Minimum length:** 12 characters
- **Complexity:** Must include uppercase letters, lowercase letters, numbers, and special characters
- **Tool:** All passwords are generated and stored using **LastPass** password manager — no passwords are reused across accounts or stored in plain text
- **Prohibition:** Passwords must never be hardcoded in source code, committed to version control, or shared via email or chat

---

## 3. Multi-Factor Authentication (MFA)

- MFA is mandatory for all accounts that support it, including Amazon Seller Central, GitHub, and Supabase
- MFA is implemented via an **authenticator app** (TOTP-based OTP) on Himanshu Dhiman's mobile device
- SMS-based OTP is used only where authenticator app is not supported

---

## 4. Password Expiration and Rotation

- All passwords must be rotated at least once every **365 days**
- SP-API credentials (client secret, refresh token, AWS IAM keys) must be rotated **annually** or immediately upon any suspected compromise
- Rotation schedule is tracked as part of the 6-month security review defined in the Incident Response Plan

### Rotation Schedule

| Account / Credential | Last Rotated | Next Rotation Due |
|----------------------|--------------|-------------------|
| Amazon Seller Central | May 2026 | May 2027 |
| Amazon SP-API credentials | May 2026 | May 2027 |
| GitHub | May 2026 | May 2027 |
| Supabase | May 2026 | May 2027 |

---

## 5. Enforcement

- Himanshu Dhiman is responsible for ensuring all accounts comply with this policy
- Compliance is reviewed annually each May and documented in this file

---

## 6. Related Documents

- `docs/incident_response_plan.md` — what to do if credentials are compromised
