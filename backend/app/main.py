import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import auth, instructors, availability_windows
from .core.constants import ALLOWED_ORIGINS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Instructly API",
    description="Backend API for Instructly - A platform connecting students with instructors",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(instructors.router)
app.include_router(availability_windows.router)

@app.on_event("startup")
async def startup_event():
    """Log application startup"""
    logger.info("Instructly API starting up...")
    logger.info(f"Allowed origins: {ALLOWED_ORIGINS}")

@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown"""
    logger.info("Instructly API shutting down...")

@app.get("/")
def read_root():
    """Root endpoint - API information"""
    return {
        "message": "Welcome to the Instructly API!",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": "instructly-api",
        "version": "1.0.0"
    }