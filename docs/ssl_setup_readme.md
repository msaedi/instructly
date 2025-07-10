# SSL/HTTPS Setup for InstaInstru Local Development

This guide explains how to run InstaInstru with HTTPS for local development.

## Quick Start

1. **Generate SSL Certificates** (one-time setup):
   ```bash
   ./setup-local-ssl.sh
   ```

2. **Start Backend Servers**:
   ```bash
   # Terminal 1 - HTTP (port 8000) with test database
   python backend/run.py

   # Terminal 2 - HTTPS (port 8001) with test database
   python backend/run_ssl.py
   ```

3. **Start Frontend**:
   ```bash
   # For HTTP mode
   npm run dev:http

   # For HTTPS mode
   npm run dev:https
   ```

4. **Access the Application**:
   - HTTP Frontend: http://localhost:3000
   - HTTPS Frontend: https://localhost:3001
   - HTTP API: http://localhost:8000
   - HTTPS API: https://localhost:8001

## Important Notes

Both HTTP and HTTPS servers use the **test database** for local development. This ensures production data is never touched during development.

## Port Configuration

| Service | HTTP | HTTPS |
|---------|------|-------|
| Backend | 8000 | 8001  |
| Frontend| 3000 | 3001  |

## Testing Login

Test that both HTTP and HTTPS work:
```bash
python backend/scripts/test_ssl_login.py
```

## Environment Variables

### Backend
Both servers automatically use test database when run with `run.py` or `run_ssl.py`.

### Frontend
The frontend scripts handle environment variables automatically:
- `npm run dev:http` - Sets up for HTTP backend
- `npm run dev:https` - Sets up for HTTPS backend

⚠️ **Note**: Always clear Next.js cache when switching between HTTP/HTTPS modes. The scripts do this automatically.

## Development Workflow

### Option 1: HTTP Only (Simpler)
```bash
# Backend
python backend/run.py

# Frontend
npm run dev:http
```

### Option 2: HTTPS Only
```bash
# Backend
python backend/run_ssl.py

# Frontend
npm run dev:https
```

### Option 3: Both (Full Testing)
Run all terminals:
1. `python backend/run.py` - HTTP API on 8000
2. `python backend/run_ssl.py` - HTTPS API on 8001
3. `npm run dev:http` - HTTP frontend on 3000
4. `npm run dev:https` - HTTPS frontend on 3001

## Scripts Overview

### Backend Scripts
- `backend/run.py` - Runs HTTP server with test database
- `backend/run_ssl.py` - Runs HTTPS server with test database
- `setup-local-ssl.sh` - Generates SSL certificates

### Frontend Scripts
- `npm run dev:http` - HTTP mode with cache clearing
- `npm run dev:https` - HTTPS mode with cache clearing

## Common Issues

1. **Certificate Warnings**: Your browser will warn about self-signed certificates. Click "Advanced" and "Proceed to localhost" to continue.

2. **Port Conflicts**: Ensure no other services are running on ports 8000, 8001, 3000, or 3001.

3. **Frontend Cache Issues**: When switching between HTTP/HTTPS, you may see "ENOENT: no such file or directory" errors. The npm scripts automatically clear the cache to prevent this.

4. **Database Connection**: Both servers use the test database. If login fails, ensure the test database is seeded:
   ```bash
   python backend/scripts/reset_and_seed_database_enhanced.py
   ```

## Cookie Configuration

The authentication system automatically configures cookies based on the protocol:
- **HTTP**: `secure=false`, `sameSite=lax`
- **HTTPS**: `secure=true`, `sameSite=none`
