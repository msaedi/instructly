# Technical Solutions Reference - Middleware & Caching

## Pure ASGI Middleware Pattern

### When to Use
- When BaseHTTPMiddleware causes timeout issues
- For better performance and control
- When multiple middleware need to work together

### Implementation Pattern
```python
class MiddlewareNameASGI:
    def __init__(self, app, config=None):
        self.app = app
        self.config = config or {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # Only handle HTTP requests
            await self.app(scope, receive, send)
            return

        # Your middleware logic here
        # scope = request data (path, method, headers, etc.)
        # receive = async function to get request body
        # send = async function to send response

        # To modify response headers:
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Modify headers here
                headers = list(message.get("headers", []))
                headers.append((b"x-custom-header", b"value"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
```

### Integration in main.py
```python
# At the end of main.py after all routes defined:
fastapi_app = app  # Keep reference for tests

# Wrap with ASGI middleware
app = MiddlewareOneASGI(app)
app = MiddlewareTwoASGI(app)

# Export both for different uses
__all__ = ['app', 'fastapi_app']
```

## Caching Serialization with Cycle Detection

### When to Use
- Serializing SQLAlchemy objects with relationships
- Preventing infinite recursion in circular references
- Caching complex object graphs

### Implementation Pattern
```python
def _serialize_for_cache(self, obj: Any, _visited: Optional[Set[int]] = None, _depth: int = 0) -> Any:
    if _visited is None:
        _visited = set()

    MAX_DEPTH = 2  # Adjust based on needs

    # Handle None
    if obj is None:
        return None

    # Handle primitives
    if isinstance(obj, (str, int, float, bool)):
        return obj

    # Handle dates/times
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()

    # Check depth to prevent deep recursion
    if _depth >= MAX_DEPTH:
        return {"_truncated": True, "_type": type(obj).__name__}

    # Handle SQLAlchemy objects
    if hasattr(obj, '__table__'):
        obj_id = id(obj)

        # Cycle detection
        if obj_id in _visited:
            # Return minimal representation for circular references
            return {
                "_circular_ref": True,
                "id": getattr(obj, 'id', None),
                "_type": obj.__class__.__name__
            }

        _visited.add(obj_id)

        # Convert to dict, handling relationships carefully
        result = {}
        for column in obj.__table__.columns:
            key = column.key
            value = getattr(obj, key, None)
            result[key] = self._serialize_for_cache(value, _visited, _depth + 1)

        # Handle specific relationships you need
        if hasattr(obj, 'student') and obj.student and _depth < MAX_DEPTH:
            result['_cached_student'] = self._serialize_for_cache(
                obj.student, _visited, _depth + 1
            )

        return result

    # Handle lists/collections
    if isinstance(obj, (list, tuple)):
        return [self._serialize_for_cache(item, _visited, _depth) for item in obj]

    # Handle dicts
    if isinstance(obj, dict):
        return {k: self._serialize_for_cache(v, _visited, _depth) for k, v in obj.items()}

    # Default: convert to string
    return str(obj)
```

### Key Principles
1. **Track Visited Objects**: Prevents infinite loops
2. **Depth Limiting**: Stop at reasonable depth
3. **Minimal Circular References**: Just enough to identify
4. **Type Preservation**: Maintain data types for correct deserialization

## Common Pitfalls to Avoid

### BaseHTTPMiddleware Issues
- **Don't**: Stack multiple BaseHTTPMiddleware
- **Don't**: Use `call_next()` for long operations
- **Do**: Convert to pure ASGI when issues arise

### Caching Serialization
- **Don't**: Try to serialize entire object graphs
- **Don't**: Ignore circular references
- **Do**: Use cycle detection
- **Do**: Limit depth appropriately

### Test Compatibility
- **Don't**: Use environment variables to change app behavior
- **Do**: Export both wrapped and unwrapped app
- **Do**: Have tests explicitly use what they need

## Performance Tips

1. **ASGI Middleware Order**: Apply in reverse (last wrapper executes first)
2. **Cache Key Design**: Include relevant parameters but keep keys reasonable
3. **Serialization Depth**: Balance between data completeness and performance
4. **Eager Loading**: Use SQLAlchemy eager loading to prevent N+1 queries

This reference captures the key patterns implemented for solving the middleware and caching issues.
