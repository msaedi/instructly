# API Standards Guide for InstaInstru

This guide ensures consistent, type-safe, and maintainable API responses across the InstaInstru platform.

## Core Principles

### 1. All Endpoints Must Use Pydantic Response Models
**NEVER return raw dictionaries or manual JSON responses**

```python
# ✅ CORRECT - Use response models
@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int) -> UserResponse:
    user_data = get_user_from_db(user_id)
    return UserResponse(**user_data)

# ❌ WRONG - Raw dictionary return
@router.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id, "name": "John"}
```

### 2. Response Model Organization
Response models are organized in dedicated schema files:

- `app/schemas/auth_responses.py` - Authentication endpoints
- `app/schemas/availability_responses.py` - Availability endpoints
- `app/schemas/booking_responses.py` - Booking endpoints
- `app/schemas/redis_monitor_responses.py` - Redis monitoring
- `app/schemas/database_monitor_responses.py` - Database monitoring
- `app/schemas/main_responses.py` - Root/health endpoints
- `app/schemas/privacy.py` - Privacy/GDPR endpoints

### 3. Response Model Patterns

#### Basic Response Model
```python
from pydantic import BaseModel, Field

class UserResponse(BaseModel):
    """Response for user endpoints."""
    id: int = Field(description="User ID")
    email: str = Field(description="User email address")
    full_name: str = Field(description="User's full name")
    role: str = Field(description="User role")
```

#### Response with Optional Fields
```python
class HealthResponse(BaseModel):
    """Response for health check endpoint."""
    status: str = Field(description="Health status")
    message: str = Field(description="Status message")
    error: Optional[str] = Field(default=None, description="Error if unhealthy")
```

#### Response with Complex Data
```python
class StatsResponse(BaseModel):
    """Response for statistics endpoint."""
    status: str
    metrics: Dict[str, Any]
    timestamp: datetime
```

## Implementation Requirements

### 1. Route Decorator Requirements
ALL routes that return data MUST include `response_model`:

```python
@router.get("/endpoint", response_model=ResponseModel)
async def endpoint_function() -> ResponseModel:
    # Implementation
    return ResponseModel(...)
```

### 2. Return Type Annotations
Functions MUST specify return type matching the response model:

```python
async def get_user(user_id: int) -> UserResponse:  # ✅ Correct
async def get_user(user_id: int):  # ❌ Missing return type
```

### 3. Exception Handling
Use proper HTTP exceptions with consistent error format:

```python
from fastapi import HTTPException, status

# For validation errors
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Invalid input data"
)

# For not found errors
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Resource not found"
)
```

## Special Cases

### 1. HTTP 204 No Content
For DELETE operations that return nothing:

```python
@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int) -> None:
    delete_user_from_db(user_id)
    return None  # No response model needed
```

### 2. Custom Response Classes
For non-JSON responses (like Prometheus metrics):

```python
@router.get("/metrics/prometheus", response_class=Response, response_model=None)
async def prometheus_metrics() -> Response:
    return Response(content=metrics_data, media_type="text/plain")
```

### 3. Conditional Responses
Use Union types for different response scenarios:

```python
from typing import Union

class ValidTokenResponse(BaseModel):
    valid: bool = True
    email: str

class InvalidTokenResponse(BaseModel):
    valid: bool = False

TokenResponse = Union[ValidTokenResponse, InvalidTokenResponse]

@router.get("/verify/{token}", response_model=TokenResponse)
async def verify_token(token: str) -> TokenResponse:
    if valid:
        return ValidTokenResponse(email=user_email)
    else:
        return InvalidTokenResponse()
```

## Testing & Validation

### 1. Contract Tests
The platform includes automated contract tests that verify:
- All endpoints declare response models
- No raw dictionary returns
- No manual JSON responses
- Consistent response structure

Run contract tests:
```bash
python -m tests.test_api_contracts
```

### 2. CI/CD Integration
Contract tests run automatically on:
- Pre-commit hooks (blocks commits with violations)
- GitHub Actions (blocks PRs with violations)
- Test suite execution

### 3. Common Violations and Fixes

#### Missing Response Model
```python
# ❌ VIOLATION
@router.get("/users")
async def get_users():
    return users

# ✅ FIX
@router.get("/users", response_model=List[UserResponse])
async def get_users() -> List[UserResponse]:
    return [UserResponse(**user) for user in users]
```

#### Direct Dictionary Return
```python
# ❌ VIOLATION
@router.get("/status", response_model=StatusResponse)
async def get_status():
    return {"status": "ok", "uptime": 3600}

# ✅ FIX
@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    return StatusResponse(status="ok", uptime=3600)
```

#### Manual JSON Response
```python
# ❌ VIOLATION
import json
return json.dumps({"data": response_data})

# ✅ FIX
return ResponseModel(data=response_data)
```

## Benefits

### 1. Type Safety
- Compile-time validation
- IDE autocomplete and error detection
- Reduces runtime errors

### 2. API Documentation
- Automatic OpenAPI/Swagger documentation
- Clear request/response contracts
- Better developer experience

### 3. Consistency
- Uniform response structure
- Predictable field names and types
- Easier frontend integration

### 4. Maintainability
- Centralized response definitions
- Easy to update API contracts
- Version control for API changes

## Getting Started

When adding a new endpoint:

1. **Define the response model** in appropriate `*_responses.py` file
2. **Add response_model parameter** to route decorator
3. **Return response model instance** from function
4. **Run contract tests** to verify compliance
5. **Test with actual API calls** to ensure functionality

## Common Patterns

### Paginated Responses
```python
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    per_page: int
    has_next: bool
```

### Error Responses
```python
class ErrorResponse(BaseModel):
    error: str
    message: str
    status_code: int
```

### Success Responses
```python
class SuccessResponse(BaseModel):
    success: bool = True
    message: str
```

This standards guide ensures that all API endpoints follow consistent patterns, making the API more predictable, maintainable, and easier to use.
