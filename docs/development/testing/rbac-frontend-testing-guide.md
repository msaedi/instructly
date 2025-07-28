# Frontend RBAC Permission Testing Guide

## Quick Manual Test Checklist

### 1. Student Login Test (john.smith@example.com)
```bash
# Login and check these UI elements:
```
- [ ] ✅ Can see "Find Instructors" menu item
- [ ] ✅ Can see "Search" functionality
- [ ] ✅ Can see "Book Now" buttons on instructor profiles
- [ ] ❌ Cannot see "Manage Availability" in menu
- [ ] ❌ Cannot see "Admin" menu
- [ ] ❌ Cannot access /admin/analytics/search (should redirect)
- [ ] ❌ Cannot access /dashboard/instructor routes

### 2. Instructor Login Test (sarah.chen@example.com)
```bash
# Login and check these UI elements:
```
- [ ] ✅ Can see "Instructor Dashboard" menu item
- [ ] ✅ Can see "Manage Availability" option
- [ ] ✅ Can see "My Bookings" with complete/cancel options
- [ ] ✅ Can access /dashboard/instructor/availability
- [ ] ❌ Cannot see "Book Now" buttons (instructors can't book)
- [ ] ❌ Cannot see "Admin" menu
- [ ] ❌ Cannot access /admin routes

### 3. Admin Login Test (admin@instainstru.com)
```bash
# Login and check these UI elements:
```
- [ ] ✅ Can see "Admin" menu item
- [ ] ✅ Can access /admin/analytics/search
- [ ] ✅ Can see all user management options
- [ ] ✅ Can book lessons (has student permissions too)
- [ ] ✅ Can manage any instructor's availability
- [ ] ✅ Can see system-wide analytics

## Browser Console Tests

### Test usePermissions Hook
```javascript
// Open browser console after login and run:

// 1. Check current permissions
const permissions = JSON.parse(localStorage.getItem('user')).permissions;
console.log('User permissions:', permissions);
console.log('Total permissions:', permissions.length);

// 2. Test hasPermission function (in React DevTools)
// Find a component using usePermissions and test:
hasPermission('create_bookings')  // Should be true for students
hasPermission('manage_availability')  // Should be true for instructors
hasPermission('view_system_analytics')  // Should be true for admin only

// 3. Check permission gates in DOM
document.querySelectorAll('[data-permission]').forEach(el => {
  console.log('Permission gate:', el.dataset.permission, 'Visible:', el.style.display !== 'none');
});
```

## Testing PermissionGate Component

### Add Test Permission Gates
```tsx
// Add these to a test page temporarily:

<PermissionGate permission="create_bookings">
  <div data-testid="student-only">Student can see this</div>
</PermissionGate>

<PermissionGate permission="manage_availability">
  <div data-testid="instructor-only">Instructor can see this</div>
</PermissionGate>

<PermissionGate permission="view_system_analytics">
  <div data-testid="admin-only">Admin can see this</div>
</PermissionGate>

<PermissionGate
  permission={["create_bookings", "manage_availability"]}
  requireAll={false}
>
  <div data-testid="student-or-instructor">Student OR Instructor can see this</div>
</PermissionGate>
```

## Network Tab Testing

### Monitor Permission Checks
1. Open Network tab in DevTools
2. Login as different users
3. Watch for:
   - `/api/auth/login` response includes permissions array
   - 403 responses when accessing forbidden endpoints
   - No permission data in request headers (should be server-side)

## Quick Smoke Test Commands

```bash
# 1. Test as Student
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john.smith@example.com","password":"Test1234"}' \
  | jq '.permissions | length'
# Should show ~10 permissions

# 2. Test as Instructor
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sarah.chen@example.com","password":"Test1234"}' \
  | jq '.permissions | length'
# Should show ~13 permissions

# 3. Test as Admin
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@instainstru.com","password":"Test1234"}' \
  | jq '.permissions | length'
# Should show all 30 permissions
```

## Expected Permission Counts
- **Student**: ~10 permissions (shared + student-specific)
- **Instructor**: ~13 permissions (shared + instructor-specific)
- **Admin**: 30 permissions (all permissions)

## Common Issues to Check

1. **Missing Permissions in Frontend**
   - Check localStorage has user object with permissions array
   - Verify useAuth hook returns permissions
   - Check AuthContext properly stores permissions

2. **Permission Gates Not Working**
   - Ensure using PermissionName enum values
   - Check permission strings match backend exactly
   - Verify usePermissions hook is imported

3. **403 Errors**
   - Check JWT token includes permissions claim
   - Verify backend permission checks are correct
   - Ensure role assignments in database

## Visual Test Matrix

| Feature | Student | Instructor | Admin |
|---------|---------|------------|-------|
| Book Lesson Button | ✅ | ❌ | ✅ |
| Manage Availability | ❌ | ✅ | ✅ |
| Admin Menu | ❌ | ❌ | ✅ |
| Search Analytics | ❌ | ❌ | ✅ |
| Complete Booking | ❌ | ✅ | ✅ |
| View All Users | ❌ | ❌ | ✅ |
