# Frontend Permission Visibility Testing

This directory contains comprehensive tests for the RBAC (Role-Based Access Control) system's frontend implementation.

## Test Coverage

### 1. `usePermissions.test.tsx`
Tests the core permission checking hook:
- **hasPermission()** - Single permission checks
- **hasAnyPermission()** - OR logic for multiple permissions
- **hasAllPermissions()** - AND logic for multiple permissions
- **Convenience methods** - Role-specific helper functions
- **PermissionGate component** - Conditional rendering
- **withPermission HOC** - Higher-order component protection

### 2. `useAdminAuth.test.ts`
Tests admin authentication and routing:
- **Authentication flow** - Login redirects
- **Permission validation** - Admin access control
- **Route protection** - Automatic redirects for unauthorized users
- **Loading states** - Proper handling during auth checks

### 3. `PermissionBasedUI.test.tsx`
Integration tests for real-world UI scenarios:
- **Student Experience** - What students see/don't see
- **Instructor Experience** - Instructor-specific UI elements
- **Admin Experience** - Full access validation
- **Unauthenticated Users** - Public vs protected content
- **Edge Cases** - Mixed permissions and loading states

## Permission Matrix Tested

| Role | Permissions | UI Elements Tested |
|------|-------------|-------------------|
| **Student** | 10 permissions | Book lessons, view bookings, search instructors |
| **Instructor** | 13 permissions | Manage profile, set availability, complete bookings |
| **Admin** | 30 permissions | All features + user management + analytics |

## Test Scenarios

### 1. **Permission Boundaries**
- Users only see UI elements they have permissions for
- Missing permissions properly hide elements
- Fallback content displays when appropriate

### 2. **Navigation Security**
- Menu items appear/disappear based on permissions
- Admin panels restricted to admin users
- Role-specific dashboards protected

### 3. **Action Authorization**
- Buttons only visible for authorized actions
- Form elements respect permission levels
- Dangerous actions (delete, manage) properly gated

### 4. **Authentication States**
- Loading states don't show protected content
- Unauthenticated users see public-only elements
- Login redirects work correctly

## Running Tests

```bash
# Run all frontend tests
npm test

# Run with coverage
npm run test:coverage

# Watch mode for development
npm run test:watch

# Run specific test file
npm test usePermissions.test.tsx
```

## Key Testing Principles

1. **Real User Scenarios**: Tests simulate actual user experiences
2. **Permission-First**: Every UI element tested for proper permission gating
3. **Security Focused**: Ensures unauthorized access is impossible
4. **Comprehensive Coverage**: All permission combinations tested

## Test Data

Tests use realistic permission sets:
- **Student**: Basic booking and viewing permissions
- **Instructor**: Profile management and lesson completion
- **Admin**: All system permissions for full access

This ensures tests reflect production permission assignments.

## Integration with Backend

These tests validate that the frontend properly interprets permissions from the backend RBAC system:
- Permissions come from JWT tokens
- UI responds to permission changes
- Security boundaries are respected

The tests mock the auth system to verify frontend behavior independently of backend state.
