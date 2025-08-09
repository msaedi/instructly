const fs = require('fs');
require('dotenv').config({ path: './scripts/.env' });

console.log('Testing R2 API access...');
console.log('Account ID:', process.env.r2_account_id);
console.log('Bucket:', process.env.r2_bucket_name);

// Simple wrangler test
const { exec } = require('child_process');
exec('wrangler r2 object list instainstru-assets --remote', (error, stdout, stderr) => {
  if (error) {
    console.error('❌ API access failed:', error);
    return;
  }
  console.log('✅ API access working!');
  console.log('Files in bucket:', stdout || '(empty)');
});
