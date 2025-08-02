# InstaInstru Quick Reference Guide

## Essential Commands

### Database Operations
```bash
# Safe operations (default to INT database)
python scripts/prep_db.py         # Setup/reset INT database
pytest -v                         # Run tests on INT database
alembic upgrade head               # Apply migrations to INT

# Local development (STG database)
./run_backend.py                   # Start backend with STG
USE_STG_DATABASE=true python scripts/prep_db.py

# Production (requires confirmation)
USE_PROD_DATABASE=true alembic upgrade head
```

### Testing
```bash
pytest -v                         # All tests
pytest -m unit                    # Unit tests only
pytest -m integration             # Integration tests only
pytest -k "booking"               # Tests matching "booking"
python -m tests.test_api_contracts # Check API compliance
```

### Development
```bash
# Backend
./run_backend.py                  # Start API server
./run_celery_worker.py            # Start background tasks
./run_flower.py                   # Start task monitoring

# Frontend
npm run dev                       # Start Next.js dev server
```

## Code Patterns

### Service Pattern
```python
class MyService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.repository = MyRepository(db)

    @measure_operation
    def create_item(self, data: dict) -> Item:
        with self.transaction():
            return self.repository.create_item(data)
```

### Route Pattern
```python
@router.post("/items/", response_model=ItemResponse)
async def create_item(
    item_data: ItemCreate,
    service: MyService = Depends(get_my_service)
) -> ItemResponse:
    item = service.create_item(item_data.model_dump())
    return ItemResponse(**item)
```

### React Query Pattern
```jsx
const { data, isLoading } = useQuery({
  queryKey: ['items', params],
  queryFn: () => api.getItems(params),
  staleTime: 5 * 60 * 1000, // 5 minutes
});
```

## Response Models (Mandatory)
```python
# ✅ CORRECT
class ItemResponse(BaseModel):
    id: int
    name: str
    created_at: datetime

@router.get("/items/{id}", response_model=ItemResponse)
async def get_item(id: int) -> ItemResponse:
    return ItemResponse(**item_data)

# ❌ WRONG - Will fail CI/CD
@router.get("/items/{id}")
async def get_item(id: int):
    return {"id": id, "name": "Item"}  # Raw dict forbidden
```

## Permissions Pattern
```python
# ✅ CORRECT - Use permissions
@router.get("/admin/data")
async def admin_data(
    user: User = Depends(require_permission(PermissionName.ADMIN_ACCESS))
):
    return data

# ❌ WRONG - Don't use role checks
if user.role == "admin":  # Bad practice
```

## Database Safety
- **Default (INT):** Safe for testing/scripts
- **STG:** Local development with `USE_STG_DATABASE=true`
- **PROD:** Requires `USE_PROD_DATABASE=true` + confirmation

## File Locations
- **Routes:** `app/routes/`
- **Services:** `app/services/`
- **Repositories:** `app/repositories/`
- **Models:** `app/models/`
- **Schemas:** `app/schemas/`
- **Tests:** `tests/`

## Key Environment Variables
```bash
# Required for development
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
SECRET_KEY=...

# Optional
RESEND_API_KEY=...
OPENAI_API_KEY=...
```

## Common Errors & Fixes

### "Contract Violation" Error
```bash
# Problem: Endpoint returning raw dict
# Fix: Add response_model and return Pydantic model
@router.get("/endpoint", response_model=MyResponse)
def endpoint() -> MyResponse:
    return MyResponse(**data)  # Not dict
```

### Database Access Error
```bash
# Problem: Trying to access wrong database
# Fix: Use appropriate environment variable
USE_STG_DATABASE=true python script.py
```

### Import Error
```bash
# Problem: Circular imports
# Fix: Use dependency injection pattern
def get_service(db: Session = Depends(get_db)) -> Service:
    return Service(db)
```

## Health Check URLs
- **API Health:** `http://localhost:8000/health`
- **Redis Health:** `http://localhost:8000/api/redis/health`
- **Database Pool:** `http://localhost:8000/api/database/pool-status`
- **API Docs:** `http://localhost:8000/docs`

## Emergency Procedures

### Reset Development Database
```bash
python scripts/prep_db.py stg  # Reset staging
```

### Check Production Health
```bash
curl https://api.instainstru.com/health
```

### View Background Tasks
```bash
./run_flower.py  # Open http://localhost:5555
```

### Check API Compliance
```bash
python -m tests.test_api_contracts  # Should show 0 violations
```

Remember: **Quality over speed** - Follow the patterns, write tests, and maintain the high standards!
