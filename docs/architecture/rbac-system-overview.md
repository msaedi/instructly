# RBAC System Overview

## Role-Based Access Control Implementation

InstaInstru uses a comprehensive Role-Based Access Control (RBAC) system with granular permissions to secure both backend APIs and frontend UI components.

## System Architecture

### Database Schema
- **roles**: Standard platform roles (student, instructor, admin)
- **permissions**: 30 granular permissions categorized by function
- **user_roles**: Many-to-many relationship between users and roles
- **role_permissions**: Many-to-many relationship between roles and permissions

### Permission Categories

#### Shared Permissions (All Authenticated Users - 5)
- `manage_own_profile` - Manage profile information
- `view_own_bookings` - View own bookings
- `view_own_search_history` - View search history
- `change_own_password` - Change password
- `delete_own_account` - Delete account

#### Student-Specific Permissions (5)
- `view_instructors` - Browse instructor profiles
- `view_instructor_availability` - See availability
- `create_bookings` - Book lessons
- `cancel_own_bookings` - Cancel bookings
- `view_booking_details` - View booking details

#### Instructor-Specific Permissions (8)
- `manage_instructor_profile` - Manage instructor profile
- `manage_services` - Manage offered services
- `manage_availability` - Set availability
- `view_incoming_bookings` - See booking requests
- `complete_bookings` - Mark lessons complete
- `cancel_student_bookings` - Cancel student bookings
- `view_own_instructor_analytics` - View analytics
- `suspend_own_instructor_account` - Self-suspend

#### Admin-Only Permissions (12)
- `view_all_users` - User management
- `manage_users` - User administration
- `view_system_analytics` - System analytics
- `export_analytics` - Export data
- `view_all_bookings` - All bookings access
- `manage_all_bookings` - Booking administration
- `access_monitoring` - System monitoring
- `moderate_content` - Content moderation
- `view_financials` - Financial data
- `manage_financials` - Financial management
- `manage_roles` - Role management
- `manage_permissions` - Permission management

## Backend Implementation

### Permission Checking
```python
from ..dependencies.permissions import require_permission
from ..core.enums import PermissionName

@router.get("/analytics")
async def get_analytics(
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS))
):
    return analytics_service.get_data()
```

### Service Layer
- **PermissionService**: Centralized permission checking
- **Role assignment**: Via migration and admin tools
- **Caching**: Permission checks are optimized for performance

## Frontend Implementation

### usePermissions Hook
```typescript
import { usePermissions } from '@/features/shared/hooks/usePermissions';
import { PermissionName } from '@/types/enums';

const { hasPermission, isAdmin } = usePermissions();

if (hasPermission(PermissionName.VIEW_SYSTEM_ANALYTICS)) {
  // Show admin dashboard
}
```

### Permission Gates
```typescript
<PermissionGate permission={PermissionName.CREATE_BOOKINGS}>
  <BookLessonButton />
</PermissionGate>
```

## Testing

### Backend Tests
- Permission matrix testing: `backend/scripts/test_rbac_permissions.py`
- Comprehensive test runner: `backend/scripts/run_rbac_tests.sh`

### Frontend Tests
- Manual testing guide: `docs/development/testing/rbac-frontend-testing-guide.md`
- Implementation summary: `docs/development/testing/rbac-implementation-summary.md`

## Key Design Decisions

1. **No Role Inheritance**: Student and Instructor roles are mutually exclusive
2. **Granular Permissions**: 30 specific permissions vs. broad role checks
3. **Permission-Based UI**: Frontend shows/hides based on permissions, not roles
4. **Backward Compatibility**: Clean migration from role-based to permission-based system

## Security Features

- **JWT Integration**: Permissions included in auth tokens
- **API Protection**: All sensitive endpoints require specific permissions
- **UI Protection**: Components hidden/shown based on user permissions
- **Admin Separation**: Clear distinction between user types and admin functions

## Migration Path

The system migrated from simple role checking to comprehensive RBAC:
1. Database schema updated with permissions tables
2. 30 permissions defined and seeded
3. Endpoints updated with permission checks
4. Frontend updated with permission-based components
5. Email whitelists removed in favor of permission checks

This provides a scalable, secure foundation for access control across the platform.
