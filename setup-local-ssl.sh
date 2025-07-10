#!/bin/bash
# setup-local-ssl.sh - Local SSL certificate setup for InstaInstru development
# Run from project root directory

echo "🔐 Setting up local SSL certificates for InstaInstru..."

# Create certificates directory
mkdir -p backend/certs
mkdir -p frontend/certs

# Check if mkcert is installed
if ! command -v mkcert &> /dev/null; then
    echo "❌ mkcert not found. Installing..."

    # Detect OS and install mkcert
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install mkcert
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # For Ubuntu/Debian
        sudo apt update
        sudo apt install libnss3-tools
        wget -O mkcert https://github.com/FiloSottile/mkcert/releases/download/v1.4.4/mkcert-linux-amd64
        chmod +x mkcert
        sudo mv mkcert /usr/local/bin/
    else
        echo "❌ Unsupported OS. Please install mkcert manually."
        exit 1
    fi
fi

# Install local CA
echo "📜 Installing local Certificate Authority..."
mkcert -install

# Generate certificates for backend
echo "🔧 Generating backend certificates..."
cd backend/certs
mkcert -cert-file cert.pem -key-file key.pem localhost 127.0.0.1 ::1 api.localhost
cd ../..

# Generate certificates for frontend
echo "🎨 Generating frontend certificates..."
cd frontend/certs
mkcert -cert-file cert.pem -key-file key.pem localhost 127.0.0.1 ::1 www.localhost
cd ../..

echo "✅ Local SSL certificates created successfully!"
echo ""
echo "📁 Certificate locations:"
echo "   Backend: backend/certs/cert.pem & backend/certs/key.pem"
echo "   Frontend: frontend/certs/cert.pem & frontend/certs/key.pem"
echo ""
echo "🚀 To run with HTTPS:"
echo "   Backend: python backend/run_ssl.py"
echo "   Frontend: npm run dev:https"
