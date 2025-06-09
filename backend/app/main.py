from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import auth, instructors, bookings, availability

app = FastAPI(
    title="Instructly API",
    description="Backend API for Instructly - A platform for managing and delivering educational content",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://instructly-ten.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(instructors.router)
app.include_router(bookings.router)
app.include_router(availability.router, prefix="/api", tags=["availability"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Instructly API!"}