# Email DNS Configuration for InstaInstru

## Critical DNS Records Required

### 1. SPF Record (Sender Policy Framework)
- **Type**: TXT
- **Host**: mail
- **Value**: `v=spf1 include:resend.com ~all`
- **Purpose**: Authorizes Resend to send emails on behalf of mail.instainstru.com

### 2. DKIM Records (DomainKeys Identified Mail)
Get these from Resend Dashboard → Settings → Domains → DNS Records (for mail.instainstru.com)
- **Type**: CNAME
- **Host**: resend._domainkey.mail
- **Value**: [Value from Resend Dashboard]
- **Purpose**: Cryptographic signature for email authentication

### 3. DMARC Record (Domain-based Message Authentication)
- **Type**: TXT
- **Host**: _dmarc.mail
- **Value**: `v=DMARC1; p=none; rua=mailto:admin@instainstru.com; ruf=mailto:admin@instainstru.com; fo=1`
- **Purpose**: Policy for handling authentication failures

## Important Notes

1. **Mail Subdomain**: We're using the mail.instainstru.com subdomain for all email sending
2. **Cloudflare Requirements**: All three records (SPF, DKIM, DMARC) must be present
3. **Propagation Time**: DNS changes can take up to 48 hours to fully propagate
4. **Domain Setup**: Add mail.instainstru.com as a separate domain in Resend Dashboard

## Current Email Senders

After implementation, InstaInstru uses these email addresses:

- **Monitoring Alerts**: `InstaInstru Alerts <alerts@mail.instainstru.com>`
- **Transactional Emails**: `InstaInstru <hello@mail.instainstru.com>`
- **Booking Notifications**: `InstaInstru Bookings <bookings@mail.instainstru.com>`
- **Password Resets**: `InstaInstru Security <security@mail.instainstru.com>`

## Verification Steps

1. After adding DNS records, verify in Resend Dashboard
2. Use MXToolbox to verify: https://mxtoolbox.com/EmailHealth.aspx
3. Send test email to: https://www.mail-tester.com/
4. Check email headers for proper DKIM signature

## Troubleshooting

### Common Issues

1. **SPF Record Conflicts**
   - Only one SPF record per domain
   - If existing SPF record exists, modify it to include `include:resend.com`

2. **DKIM Not Verifying**
   - Ensure CNAME record points to correct Resend value
   - Check for trailing dots in DNS records

3. **DMARC Policy Too Strict**
   - Start with `p=none` for monitoring
   - Gradually move to `p=quarantine` then `p=reject`

### Testing Commands

```bash
# Check SPF record
dig txt mail.instainstru.com | grep spf

# Check DKIM record
dig cname resend._domainkey.mail.instainstru.com

# Check DMARC record
dig txt _dmarc.mail.instainstru.com
```

## Implementation Checklist

- [ ] Add SPF record to DNS
- [ ] Add DKIM CNAME record from Resend Dashboard
- [ ] Add DMARC record to DNS
- [ ] Verify all records in Resend Dashboard
- [ ] Test email delivery with mail-tester.com
- [ ] Monitor bounce rates and deliverability
- [ ] Update environment variables with new sender addresses
