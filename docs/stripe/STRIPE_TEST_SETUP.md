# Stripe Test Account Setup

This document explains how to manage Stripe test accounts across database reseeds during development.

## Overview

During development, we frequently reseed the database which generates new ULIDs for all records. However, Stripe Connected Account IDs remain constant in Stripe's system. This mapping system preserves the association between instructors and their Stripe accounts across database reseeds.

## How It Works

1. **Mapping File**: `backend/config/stripe_test_accounts.json` stores email-to-Stripe-account-ID mappings
2. **Automatic Restoration**: When seeding, the script checks this file and restores Stripe associations
3. **Helper Script**: Updates the mapping file with new onboarded instructors

## File Structure

```json
{
  "_comment": "Test Stripe Connected Account mappings - DO NOT COMMIT with real account IDs",
  "sarah.chen@example.com": "acct_1234567890abcdef",
  "michael.rodriguez@example.com": null,
  ...
}
```

- `null` values indicate instructors who haven't been onboarded yet
- Actual account IDs are stored after onboarding

## Usage

### Initial Setup

1. The mapping file is created with placeholder entries for all test instructors
2. Initially, all values are `null` (no Stripe accounts connected)

### Onboarding a Test Instructor

1. Log in as an instructor (e.g., `sarah.chen@example.com` / `Test1234`)
2. Navigate to the instructor dashboard
3. Click "Connect Stripe Account" in the Payment Settings section
4. Complete the Stripe onboarding flow
5. The instructor now has a Stripe account ID in the database

### Preserving Stripe Accounts

After onboarding instructors, run the update script to save their Stripe account IDs:

```bash
# From backend directory
python scripts/update_stripe_mapping.py

# Or with specific database
USE_STG_DATABASE=true python scripts/update_stripe_mapping.py
```

This updates `config/stripe_test_accounts.json` with the current Stripe account associations.

### Reseeding with Preserved Accounts

When you reseed the database:

```bash
# The seed script automatically reads the mapping file
python scripts/reset_and_seed_yaml.py

# Or for staging
USE_STG_DATABASE=true python scripts/reset_and_seed_yaml.py
```

The script will:
1. Load the mapping file
2. Create instructor profiles as usual
3. If an instructor's email has a Stripe account ID in the mapping, create a `stripe_connected_accounts` record
4. Log which instructors were linked to existing Stripe accounts

Output example:
```
📦 Loaded Stripe account mappings for 12 instructors
...
  ✅ Created instructor: Sarah Chen with 3 services
    💳 Linked to existing Stripe account: acct_1234567890ab...
```

### Viewing Current Mappings

To see which instructors have Stripe accounts:

```bash
python scripts/update_stripe_mapping.py
```

This shows:
- Total instructors in the system
- How many are connected to Stripe
- Which specific instructors have accounts

## Important Notes

### Development Only

This system is for **development and testing only**. In production:
- Stripe account IDs are created once and stored permanently
- No mapping file is used or needed
- Database backups preserve all associations

### Security

- **NEVER commit real Stripe account IDs** to version control
- The mapping file is in `.gitignore` to prevent accidental commits
- Only use test mode Stripe accounts in development

### Test vs Production

- **Test Mode**: Uses Stripe test keys, test account IDs (format: `acct_test_...`)
- **Production**: Uses live Stripe keys, real account IDs (format: `acct_...`)
- Never mix test and production account IDs

## Workflow Example

1. **Fresh Start**: Database is empty, mapping file has all `null` values

2. **Onboard Instructors**:
   - Log in as `sarah.chen@example.com`
   - Complete Stripe onboarding
   - Log in as `michael.rodriguez@example.com`
   - Complete Stripe onboarding

3. **Save Mappings**:
   ```bash
   python scripts/update_stripe_mapping.py
   ```

4. **Work on Features**: Develop, test, break things

5. **Reseed Database**:
   ```bash
   python scripts/reset_and_seed_yaml.py
   ```
   Sarah and Michael's Stripe accounts are automatically restored!

6. **Continue Development**: No need to re-onboard instructors

## Troubleshooting

### Mapping File Not Found

If you see: `ℹ️  No Stripe account mapping file found`

Create the file manually or copy from the template:
```bash
cp backend/config/stripe_test_accounts.json.example backend/config/stripe_test_accounts.json
```

### Stripe Account Not Restored

If an instructor's Stripe account isn't restored after reseeding:

1. Check the mapping file has their email and account ID
2. Ensure the email matches exactly (case-sensitive)
3. Run the update script to refresh mappings
4. Check for any error messages during seeding

### Can't Onboard Instructor

If Stripe onboarding fails:

1. Ensure you're using test mode Stripe keys in `.env`
2. Check the frontend is configured with the correct API URL
3. Verify the instructor profile exists in the database
4. Check browser console for errors

## Programmatic Account Creation

### Option 1: Full Test Accounts (Development Only)

For development, you can create fully functional test accounts programmatically:

```bash
# Create test accounts for ALL instructors
python scripts/create_test_stripe_accounts.py

# Dry run to see what would be created
python scripts/create_test_stripe_accounts.py --dry-run
```

**Requirements:**
- Must use Stripe TEST keys (`sk_test_...`)
- Accounts are auto-approved with fake test data
- Fully functional for testing payments in test mode
- Cannot be used in production

### Option 2: Prefilled Accounts (Production-Ready)

Create skeleton accounts that instructors must complete:

```bash
# Create for specific instructor
python scripts/create_stripe_prefilled_accounts.py --email sarah.chen@example.com

# Create for multiple instructors (default limit: 5)
python scripts/create_stripe_prefilled_accounts.py --all --limit 10
```

This creates:
- A Stripe Connect account with basic info
- An onboarding URL for the instructor to complete setup
- Database record with `onboarding_completed=false`

The script outputs onboarding URLs that you can send to instructors.

### Why Can't We Fully Automate Production Accounts?

Stripe requires real human verification for:
- **Identity**: SSN/EIN verification
- **Banking**: Bank account ownership
- **Compliance**: Terms of Service acceptance
- **Risk**: Address and business verification

Test mode bypasses these requirements, but production mode cannot.

## Related Files

- `backend/config/stripe_test_accounts.json` - The mapping file
- `backend/scripts/reset_and_seed_yaml.py` - Seed script that reads mappings
- `backend/scripts/update_stripe_mapping.py` - Updates mapping from database
- `backend/scripts/create_test_stripe_accounts.py` - Create full test accounts
- `backend/scripts/create_stripe_prefilled_accounts.py` - Create skeleton accounts
- `backend/.gitignore` - Ensures mapping file isn't committed
