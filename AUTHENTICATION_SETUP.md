# Authentication Setup Guide

## User Type Hierarchy

Your OfficeFlow application now has three user types:

1. **Super Admin** (Django superuser)

   - Full system access
   - Can create HR users
   - Can access Django admin panel

2. **HR Users** (staff=True, group='HR')

   - Can access /manage/ URLs (admin pages)
   - Can onboard new employees
   - Can view and edit all employee data
   - Can access employee directory

3. **Employee Users** (staff=False, group='Employee')
   - Can only view their own profile and data
   - Cannot access /manage/ URLs
   - Cannot edit critical information

## Initial Setup

### 1. Create Groups (Run Once)

```bash
python manage.py shell
```

```python
from django.contrib.auth.models import Group
Group.objects.get_or_create(name='HR')
Group.objects.get_or_create(name='Employee')
exit()
```

### 2. Create Super Admin

```bash
python manage.py createsuperuser
```

Follow the prompts to create your admin account.

### 3. Create HR Users

1. Login as superuser at: http://localhost:8000/login/
2. Navigate to: http://localhost:8000/hr/create/
3. Fill in the form to create HR users

## Employee Onboarding Flow

### For HR Staff:

1. Login to the system
2. Go to "Employees Directory" or navigate to: http://localhost:8000/employees/onboarding/
3. Fill out the onboarding form
4. **Important**: After submission, a popup will show:
   - Temporary username (usually Employee ID)
   - Auto-generated temporary password
   - Copy these credentials and share them securely with the new employee

### For New Employees:

1. Receive login credentials from HR
2. Go to: http://localhost:8000/login/
3. Login with provided username and password
4. Change password at: http://localhost:8000/change-password/

## URL Structure

### Public URLs:

- `/login/` - Login page
- `/logout/` - Logout

### Protected URLs (Authenticated Users):

- `/` - Landing page (redirects based on user type)
- `/change-password/` - Change password

### HR/Admin Only URLs:

- `/hr/create/` - Create new HR users (superuser only)
- `/employees/directory/` - Employee directory
- `/employees/onboarding/` - Onboard new employees
- `/manage/employees/<id>/general/` - Edit employee info
- `/manage/employees/<id>/job/` - Edit job details
- `/manage/employees/<id>/payroll/` - Edit payroll info
- `/manage/employees/<id>/documents/` - Manage documents

### Employee URLs (Own data only):

- `/employees/<employee_id>/dashboard/` - Dashboard
- `/employees/<employee_id>/general/` - View profile
- `/employees/<employee_id>/job/` - View job details
- `/employees/<employee_id>/payroll/` - View payroll
- `/employees/<employee_id>/attendance/` - Clock in/out
- `/employees/<employee_id>/schedule/` - View schedule
- `/employees/<employee_id>/documents/` - View documents
- `/employees/<employee_id>/payslips/` - View payslips

## Security Features

1. **Authentication Required**: All employee pages require login
2. **Authorization Checks**: Employees can only access their own data
3. **Admin Protection**: /manage/ URLs restricted to HR users only
4. **Password Security**:
   - Auto-generated secure temporary passwords
   - Users encouraged to change password on first login
5. **Session Management**: Proper login/logout flow

## Testing

### Test Super Admin:

1. Create superuser
2. Login at /login/
3. Should redirect to Django admin

### Test HR User:

1. Create HR user via /hr/create/
2. Login as HR user
3. Should redirect to employee directory
4. Can access /manage/ URLs

### Test Employee User:

1. Onboard an employee
2. Login with provided credentials
3. Should redirect to employee dashboard
4. Cannot access other employees' pages
5. Cannot access /manage/ URLs

## Troubleshooting

**Issue**: "You don't have permission to access this page"

- Solution: Check if user is in correct group (HR or Employee)

**Issue**: Employee can't login

- Solution: Verify credentials are correct, check if user account exists

**Issue**: HR user can't access /manage/ URLs

- Solution: Verify user is in 'HR' group and has is_staff=True

## Next Steps

1. Set up email (optional) to automatically send credentials
2. Customize login page branding
3. Add password reset functionality
4. Implement 2FA (optional)
