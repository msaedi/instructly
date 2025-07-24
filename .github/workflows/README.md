# GitHub Actions Workflows

This directory contains GitHub Actions workflows for automating various tasks in the InstaInstru platform.

## Workflows

### 1. Daily Analytics Calculation (`daily-analytics.yml`)

**Purpose**: Automatically calculates service analytics every day at 2 AM EST.

**Schedule**: Runs daily at 7:00 AM UTC (2:00 AM EST)

**Features**:
- Calculates analytics for the last 30 days by default
- Can be manually triggered with custom parameters
- Creates GitHub issues on failure
- Sends success notifications

**Manual Trigger**:
1. Go to the [Actions tab](../../actions)
2. Select "Daily Analytics Calculation"
3. Click "Run workflow"
4. (Optional) Change the number of days to analyze
5. Click the green "Run workflow" button

### 2. Test Analytics Calculation (`test-analytics.yml`)

**Purpose**: Manually test analytics calculation before waiting for the daily schedule.

**Features**:
- Manual trigger only (no schedule)
- Choose between test and production database
- Configurable number of days to analyze
- Uploads artifacts for debugging
- Creates a summary in the workflow run

**Usage**:
1. Go to the [Actions tab](../../actions)
2. Select "Test Analytics Calculation"
3. Click "Run workflow"
4. Configure options:
   - `days_back`: Number of days to analyze (default: 7)
   - `use_test_database`: Whether to use test database (default: false)
5. Click "Run workflow"

## Required Secrets

Before these workflows can run successfully, you need to add the following secrets to your repository:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** for each:

| Secret Name | Description | Example |
|------------|-------------|---------|
| `DATABASE_URL` | Production database connection string | `postgresql://user:pass@host:5432/dbname` |
| `TEST_DATABASE_URL` | Test database connection string (optional) | `postgresql://user:pass@host:5432/test_dbname` |
| `REDIS_URL` | Redis connection string for caching | `redis://localhost:6379/0` |
| `SECRET_KEY` | Application secret key | `your-secret-key-here` |
| `RESEND_API_KEY` | Email service API key | `re_123456789` |

## Monitoring Workflow Execution

### View Workflow Runs
1. Go to the [Actions tab](../../actions)
2. Select a workflow to see its runs
3. Click on a specific run to see details

### Notifications
- **Email**: GitHub sends emails on workflow failures by default
- **Issues**: The daily analytics workflow creates issues on failure
- **Slack/Discord**: Can be added using additional actions

### Debugging Failed Runs
1. Click on the failed workflow run
2. Expand the failed step to see logs
3. Check the "Summary" section for quick overview
4. Download artifacts if available (test workflow only)

## Best Practices

### Security
- Never hardcode secrets in workflow files
- Use repository secrets for sensitive data
- Limit secret access to required workflows

### Testing
- Always test with the test workflow first
- Use a test database for experimentation
- Start with a small number of days for faster runs

### Maintenance
- Review workflow logs regularly
- Update Python version as needed
- Keep dependencies up to date

## Comparison with Celery

### GitHub Actions Advantages
- **Serverless**: No infrastructure to manage
- **Free tier**: 2,000 minutes/month for private repos
- **Built-in**: No additional services needed
- **Simple**: Easy to set up and monitor

### Celery Advantages
- **Real-time**: Can process tasks immediately
- **Flexibility**: More complex scheduling options
- **Scale**: Better for high-frequency tasks
- **Control**: More retry and routing options

### When to Use Each
- **GitHub Actions**: Daily/hourly scheduled tasks, simple workflows
- **Celery**: Real-time processing, complex task dependencies, frequent execution

## Troubleshooting

### Common Issues

1. **Workflow not triggering**
   - Check if Actions are enabled in repository settings
   - Verify cron syntax for scheduled workflows
   - Ensure workflow file is in default branch

2. **Secret not found**
   - Verify secret name matches exactly (case-sensitive)
   - Check secret is added to repository, not user settings
   - Ensure no extra spaces in secret values

3. **Database connection fails**
   - Verify DATABASE_URL format
   - Check network access (GitHub IPs may need whitelisting)
   - Test connection string locally first

### Getting Help

1. Check [GitHub Actions documentation](https://docs.github.com/en/actions)
2. Review workflow logs for specific errors
3. Create an issue in this repository
4. Check GitHub Status for service issues

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Workflow Syntax Reference](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions)
- [GitHub Actions Marketplace](https://github.com/marketplace?type=actions)
- [Cron Expression Generator](https://crontab.guru/)
