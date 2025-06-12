import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import auth, instructors, availability_windows, password_reset, bookings
from .core.constants import (
    ALLOWED_ORIGINS, 
    BRAND_NAME, 
    API_TITLE, 
    API_DESCRIPTION, 
    API_VERSION
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
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
app.include_router(password_reset.router)
app.include_router(bookings.router)

@app.on_event("startup")
async def startup_event():
    """Log application startup"""
    logger.info(f"{BRAND_NAME} API starting up...")
    logger.info(f"Allowed origins: {ALLOWED_ORIGINS}")

@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown"""
    logger.info(f"{BRAND_NAME} API shutting down...")

@app.get("/")
def read_root():
    """Root endpoint - API information"""
    return {
        "message": f"Welcome to the {BRAND_NAME} API!",
        "version": API_VERSION,
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": f"{BRAND_NAME.lower()}-api",
        "version": API_VERSION
    }