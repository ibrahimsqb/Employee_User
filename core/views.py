from django.contrib.auth.models import User, Group
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
import secrets
import base64

from .forms import BankDetailForm, EmployeeDocumentForm
from .models import (
    BankDetail,
    EmployeeAttendance,
    EmployeeDocument,
    EmployeeOnboarding,
    EmployeePersonalInfo,
    EmployeeProfile,
    EmploymentContract,
    JobHistory,
    Payroll,
    SalaryComponent,
    WorkSchedule,
)
from . import face_api


# ================= PERMISSION HELPERS =================

def is_hr_or_superuser(user):
    """Check if user is HR staff or superuser."""
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name='HR').exists())

def is_superuser(user):
    """Check if user is superuser."""
    return user.is_authenticated and user.is_superuser

def can_access_employee(user, employee_id):
    """Check if user can access this employee's data."""
    if not user.is_authenticated:
        return False
    
    if user.is_superuser or user.groups.filter(name='HR').exists():
        return True
    
    # Regular employees can only access their own data
    try:
        profile = EmployeeProfile.objects.get(user=user)
        return profile.employee_id == employee_id
    except EmployeeProfile.DoesNotExist:
        return False


# ================= AUTHENTICATION VIEWS =================

def login_view(request):
    """Custom login view."""
    if request.user.is_authenticated:
        # Redirect based on user type
        if request.user.is_superuser:
            return redirect("admin:index")
        elif request.user.groups.filter(name='HR').exists():
            return redirect("employee_directory")
        else:
            try:
                profile = EmployeeProfile.objects.get(user=request.user)
                return redirect("employee_dashboard", employee_id=profile.employee_id)
            except EmployeeProfile.DoesNotExist:
                pass
    
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            # Redirect based on user type
            if user.is_superuser:
                return redirect("admin:index")
            elif user.groups.filter(name='HR').exists():
                return redirect("employee_directory")
            else:
                # Regular employee - redirect to their dashboard
                try:
                    profile = EmployeeProfile.objects.get(user=user)
                    return redirect("employee_dashboard", employee_id=profile.employee_id)
                except EmployeeProfile.DoesNotExist:
                    messages.error(request, "Employee profile not found.")
                    logout(request)
                    return redirect("login")
        else:
            messages.error(request, "Invalid username or password.")
    
    return render(request, "core/login.html")

def logout_view(request):
    """Custom logout view."""
    logout(request)
    return redirect("login")

@login_required
def change_password_view(request):
    """Allow users to change their password."""
    if request.method == "POST":
        old_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")
        
        if new_password != confirm_password:
            messages.error(request, "New passwords don't match.")
        elif request.user.check_password(old_password):
            request.user.set_password(new_password)
            request.user.save()
            messages.success(request, "Password changed successfully. Please login again.")
            return redirect("login")
        else:
            messages.error(request, "Incorrect old password.")
    
    return render(request, "core/change_password.html")

@login_required
@user_passes_test(is_superuser)
def create_hr_user_view(request):
    """Admin view to create HR users."""
    
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        full_name = request.POST.get("full_name", "")
        
        try:
            # Create HR user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=True  # HR users are staff
            )
            
            first, *rest = full_name.split(" ", 1) if full_name else ["", ""]
            user.first_name = first
            user.last_name = rest[0] if rest else ""
            user.save()
            
            # Add to HR group
            hr_group, _ = Group.objects.get_or_create(name='HR')
            user.groups.add(hr_group)
            
            messages.success(request, f"HR user '{username}' created successfully.")
            return redirect("create_hr_user")
        except Exception as e:
            messages.error(request, f"Error creating HR user: {str(e)}")
    
    return render(request, "adminPages/create_hr_user.html")


# ================= PUBLIC VIEWS =================


def index(request):
    """Landing page - redirect based on user type."""
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("admin:index")
        elif request.user.groups.filter(name='HR').exists():
            return redirect("employee_directory")
        else:
            try:
                profile = EmployeeProfile.objects.get(user=request.user)
                return redirect("employee_dashboard", employee_id=profile.employee_id)
            except EmployeeProfile.DoesNotExist:
                pass
    return redirect("login")


@login_required
@user_passes_test(is_hr_or_superuser)
def employee_directory_view(request):
    """Display all employees in a directory/grid view."""
    employees = EmployeeProfile.objects.select_related('employeepersonalinfo').all()
    context = {
        'employees': employees,
    }
    return render(request, "adminPages/employee_directory.html", context)


def _generate_next_employee_id() -> str:
    """Generate the next employee ID like EMP-001, EMP-002, ..."""

    last_profile = (
        EmployeeProfile.objects.filter(employee_id__startswith="EMP-")
        .order_by("-id")
        .first()
    )

    if not last_profile:
        return "EMP-001"

    last_id = last_profile.employee_id or ""
    try:
        number_part = int(last_id.split("-")[-1])
    except (ValueError, TypeError):
        # Fallback if existing IDs don't match the pattern cleanly
        return "EMP-001"

    return f"EMP-{number_part + 1:03d}"


@transaction.atomic
@login_required
@user_passes_test(is_hr_or_superuser)
def employee_onboarding_view(request):
    """Create a new employee and all related records from the onboarding form."""

    if request.method == "POST":
        data = request.POST

        full_name = (data.get("full_name") or "").strip() or "New Employee"
        email = data.get("email") or ""
        employee_id = data.get("employee_id") or _generate_next_employee_id()
        username = employee_id or email or full_name.replace(" ", "_")

        # Generate a random temporary password
        temp_password = secrets.token_urlsafe(12)

        # Create user with temporary password
        user = User.objects.create_user(
            username=username,
            email=email,
            password=temp_password,
            is_staff=False  # Employees are not staff by default
        )
        
        first, *rest = full_name.split(" ", 1)
        user.first_name = first
        user.last_name = rest[0] if rest else ""
        user.save()

        # Add user to Employee group
        employee_group, _ = Group.objects.get_or_create(name='Employee')
        user.groups.add(employee_group)

        # Employee profile
        from datetime import date

        join_date_str = data.get("join_date") or None
        join_date = None
        if join_date_str:
            try:
                join_date = date.fromisoformat(join_date_str)
            except ValueError:
                join_date = None

        # Map employment type text to model choice key if possible
        employment_type_map = {
            "full time": "FULL_TIME",
            "part time": "PART_TIME",
            "contract": "CONTRACT",
        }
        employment_type_raw = (data.get("employment_type") or "").lower()
        employment_type = employment_type_map.get(employment_type_raw, "FULL_TIME")

        status_map = {
            "active": "ACTIVE",
            "inactive": "INACTIVE",
        }
        status_raw = (data.get("employment_status") or "").lower()
        status = status_map.get(status_raw, "ACTIVE")

        profile = EmployeeProfile.objects.create(
            user=user,
            employee_id=employee_id,
            department=data.get("department") or "",
            job_title=data.get("job_title") or "",
            office=data.get("office") or "",
            employment_type=employment_type,
            status=status,
            join_date=join_date or date.today(),
        )

        # Personal info
        dob_str = data.get("date_of_birth") or None
        dob = None
        if dob_str:
            try:
                dob = date.fromisoformat(dob_str)
            except ValueError:
                dob = None

        EmployeePersonalInfo.objects.create(
            employee=profile,
            full_name=full_name,
            gender=(data.get("gender") or "OTHER").upper(),
            date_of_birth=dob or date(2000, 1, 1),
            marital_status=data.get("marital_status") or "",
            email=email,
            phone_number=data.get("phone_number") or "",
            personal_id=data.get("personal_id") or "",
            emergency_contact=data.get("emergency_contact") or "",
            timezone=data.get("time_zone") or "UTC+5",
        )

        # Onboarding record
        EmployeeOnboarding.objects.create(
            employee=profile,
            manager=request.user if request.user.is_authenticated else None,
            joining_date=join_date or date.today(),
            welcome_session_completed=bool(data.get("orientation_welcome")),
            safety_training_completed=bool(data.get("orientation_safety")),
            culture_training_completed=bool(data.get("orientation_culture")),
        )

        # Initial job history
        JobHistory.objects.create(
            employee=profile,
            effective_date=join_date or date.today(),
            job_title=data.get("job_title") or "",
            position_type=data.get("position_type") or "",
            employment_type=employment_type,
            line_manager=data.get("line_manager") or "",
        )

        # Employment contract
        start_str = data.get("contract_start") or None
        end_str = data.get("contract_end") or None
        start_date = end_date = None
        if start_str:
            try:
                start_date = date.fromisoformat(start_str)
            except ValueError:
                start_date = None
        if end_str:
            try:
                end_date = date.fromisoformat(end_str)
            except ValueError:
                end_date = None

        EmploymentContract.objects.create(
            employee=profile,
            contract_number=data.get("contract_number") or "",
            contract_name=data.get("contract_name") or "",
            contract_type=data.get("contract_type") or "",
            start_date=start_date or (join_date or date.today()),
            end_date=end_date,
        )

        # Work schedule
        WorkSchedule.objects.create(
            employee=profile,
            working_hours=data.get("working_hours") or "9:00am - 5:00pm",
            working_days=data.get("working_days") or "Monday - Friday",
        )

        # Bank details
        BankDetail.objects.create(
            employee=profile,
            bank_name=data.get("bank_name") or "",
            account_title=data.get("account_title") or full_name,
            account_number=data.get("account_number") or "",
            iban=data.get("iban") or "",
            payment_frequency=data.get("payment_frequency") or "MONTHLY",
        )

        # Salary components: map from onboarding fields
        def create_component(field_name: str, label: str, component_type: str):
            raw = data.get(field_name)
            if raw:
                try:
                    amount = float(
                        raw.replace(",", "").replace("Rs.", "").replace(" ", "")
                    )
                except ValueError:
                    return
                SalaryComponent.objects.create(
                    employee=profile,
                    name=label,
                    amount=amount,
                    component_type=component_type,
                )

        create_component("basic_salary", "Basic Salary", "EARNING")
        create_component("house_allowance", "House Allowance", "EARNING")
        create_component("medical_allowance", "Medical Allowance", "EARNING")
        create_component("transport_allowance", "Transport Allowance", "EARNING")
        create_component("bonus", "Bonus", "EARNING")
        create_component("tax_deduction", "Tax Deduction", "DEDUCTION")
        create_component("loan_deduction", "Loan Deduction", "DEDUCTION")

        # Documents uploaded at onboarding time
        cnic_file = request.FILES.get("cnic_file")
        if cnic_file:
            EmployeeDocument.objects.create(
                employee=profile,
                name="CNIC / ID Copy",
                category="IDENTITY",
                file=cnic_file,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )

        contract_file = request.FILES.get("contract_file")
        if contract_file:
            EmployeeDocument.objects.create(
                employee=profile,
                name="Employment Contract / Offer Letter",
                category="CONTRACT",
                file=contract_file,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )

        # Enroll facial data with external face recognition API
        face_images = [img for img in request.FILES.getlist("face_images") if img]
        if face_images:
            try:
                # Use employee_id as the canonical person_name for matching
                face_api.add_person(profile.employee_id, face_images)
                # Rebuild internal index and run migrations after enrollment
                try:
                    face_api.rebuild_db()
                    face_api.migrate()
                except face_api.FaceAPIError:
                    # Non-critical; enrollment already done, can retry later
                    pass
                messages.success(request, "Facial data enrolled for attendance.")
            except face_api.FaceAPIError as exc:
                messages.warning(
                    request,
                    f"Employee created but face enrollment failed: {exc}",
                )
        else:
            messages.warning(
                request,
                "Employee created but no facial images were uploaded for attendance enrollment.",
            )

        # Store temporary password in session for display
        request.session['new_employee_credentials'] = {
            'username': username,
            'password': temp_password,
            'email': email,
            'full_name': full_name
        }

        # Redirect to the employee directory
        return redirect("employee_general", employee_id=profile.employee_id)

    # GET: just render the static onboarding form
    default_employee_id = _generate_next_employee_id()
    return render(
        request,
        "adminPages/employee_onboarding.html",
        {"default_employee_id": default_employee_id},
    )


def _get_employee_or_404(employee_id: str) -> EmployeeProfile:
    return get_object_or_404(EmployeeProfile, employee_id=employee_id)


def _mask_account(number: str) -> str:
    if not number:
        return ""
    num = str(number)
    if len(num) <= 2:
        return num
    return num[:2] + "*" * (len(num) - 2)


def _ensure_current_month_payroll(employee: EmployeeProfile) -> Payroll | None:
    """Guarantee a payroll exists for the current month; create it if missing."""
    from datetime import date
    from calendar import monthrange
    from django.db.models import Sum

    today = date.today()
    existing = Payroll.objects.filter(
        employee=employee, period_end__year=today.year, period_end__month=today.month
    ).first()
    if existing:
        return existing

    earnings_total = (
        SalaryComponent.objects.filter(employee=employee, component_type="EARNING")
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    deductions_total = (
        SalaryComponent.objects.filter(employee=employee, component_type="DEDUCTION")
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )

    period_start = date(today.year, today.month, 1)
    period_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
    payment_method = "Bank Transfer"

    bank = getattr(employee, "bankdetail", None)
    if bank and getattr(bank, "payment_frequency", None):
        payment_method = f"Bank Transfer ({bank.payment_frequency.title()})"

    return Payroll.objects.create(
        employee=employee,
        period_start=period_start,
        period_end=period_end,
        total_earnings=earnings_total,
        total_deductions=deductions_total,
        net_salary=earnings_total - deductions_total,
        payment_method=payment_method,
        payment_date=today,
    )


def employee_dashboard_view(request, employee_id):
    """Display employee dashboard."""
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")
    
    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)

    context = {
        "employee": employee,
        "personal": personal,
    }
    return render(request, "employeePages/employee_dashboard.html", context)


def employee_general_view(request, employee_id):
    """Display employee general/personal information."""
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")
    
    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)
    
    # Check if there are new employee credentials to display
    credentials = request.session.pop('new_employee_credentials', None)
    
    context = {
        "employee": employee,
        "personal": personal,
        "credentials": credentials,
    }
    return render(request, "employeePages/employee1.html", context)


def employee_job_view(request, employee_id):
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")
    
    employee = _get_employee_or_404(employee_id)
    job_history = JobHistory.objects.filter(employee=employee).order_by("-effective_date")
    contracts = EmploymentContract.objects.filter(employee=employee).order_by("-start_date")
    schedule = getattr(employee, "workschedule", None)
    from datetime import date

    today = date.today()
    service_years = None
    if employee.join_date:
        service_years = (today - employee.join_date).days // 365
    context = {
        "employee": employee,
        "job_history": job_history,
        "contracts": contracts,
        "schedule": schedule,
        "service_years": service_years,
    }
    return render(request, "employeePages/employee2.html", context)


def employee_payroll_view(request, employee_id):
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")
    
    employee = _get_employee_or_404(employee_id)
    earnings = SalaryComponent.objects.filter(employee=employee, component_type="EARNING")
    deductions = SalaryComponent.objects.filter(employee=employee, component_type="DEDUCTION")
    bank = getattr(employee, "bankdetail", None)
    _ensure_current_month_payroll(employee)
    payroll_history = Payroll.objects.filter(employee=employee).order_by("-payment_date")

    last_pay = payroll_history.first()

    from django.db.models import Sum

    earnings_total = earnings.aggregate(total=Sum("amount"))["total"] or 0
    deductions_total = deductions.aggregate(total=Sum("amount"))["total"] or 0
    
    # Calculate what the net salary will be for future payslips
    calculated_net_salary = earnings_total - deductions_total

    context = {
        "employee": employee,
        "earnings": earnings,
        "deductions": deductions,
        "bank": bank,
        "payroll_history": payroll_history,
        "last_pay": last_pay,
        "earnings_total": earnings_total,
        "deductions_total": deductions_total,
        "calculated_net_salary": calculated_net_salary,
    }
    return render(request, "employeePages/employee3.html", context)


def employee_payslip_list_view(request, employee_id):
    """Display a list of all payslips for an employee."""
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")
    
    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)
    _ensure_current_month_payroll(employee)
    payroll_records = Payroll.objects.filter(employee=employee).order_by("-payment_date")

    context = {
        "employee": employee,
        "personal": personal,
        "payroll_records": payroll_records,
    }
    return render(request, "employeePages/payslip_list.html", context)


def employee_payslip_detail_view(request, employee_id, payroll_id):
    """Display a single payslip detail."""
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")
    
    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)
    bank = getattr(employee, "bankdetail", None)

    payroll = get_object_or_404(Payroll, employee=employee, id=payroll_id)

    # Only show component breakdown for current month's payslip
    # Past payslips will only show totals to prevent showing updated values
    from datetime import date
    today = date.today()
    is_current_month = (payroll.period_end.year == today.year and 
                        payroll.period_end.month == today.month)
    
    earnings = None
    deductions = None
    if is_current_month:
        earnings = SalaryComponent.objects.filter(employee=employee, component_type="EARNING")
        deductions = SalaryComponent.objects.filter(employee=employee, component_type="DEDUCTION")

    context = {
        "employee": employee,
        "personal": personal,
        "payroll": payroll,
        "earnings": earnings,
        "deductions": deductions,
        "bank": bank,
        "masked_account": _mask_account(bank.account_number) if bank else "",
        "masked_iban": _mask_account(bank.iban) if bank else "",
        "is_current_month": is_current_month,
    }
    return render(request, "employeePages/payslip.html", context)


def employee_documents_view(request, employee_id):
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")
    
    employee = _get_employee_or_404(employee_id)
    documents = EmployeeDocument.objects.filter(employee=employee).order_by("-uploaded_at")

    if request.method == "POST":
        form = EmployeeDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.employee = employee
            doc.uploaded_by = request.user if request.user.is_authenticated else None
            doc.save()
            return redirect("employee_documents", employee_id=employee.employee_id)
    else:
        form = EmployeeDocumentForm()

    context = {
        "employee": employee,
        "documents": documents,
        "form": form,
    }
    return render(request, "employeePages/employee4.html", context)


def employee_attendance_view(request, employee_id):
    """Track daily attendance for an employee (check-in / check-out)."""
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")

    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)

    today = timezone.localdate()
    now = timezone.localtime()

    attendance, _ = EmployeeAttendance.objects.get_or_create(
        employee=employee,
        date=today,
    )

    def _decode_base64_image(data_uri: str) -> bytes:
        if not data_uri:
            raise ValueError("No image data provided")
        if "," in data_uri:
            data_uri = data_uri.split(",", 1)[1]
        return base64.b64decode(data_uri)

    if request.method == "POST":
        action = request.POST.get("action")
        captured_image = request.POST.get("captured_image")

        if action not in {"check_in", "check_out"}:
            messages.error(request, "Invalid attendance action.")
            return redirect("employee_attendance", employee_id=employee.employee_id)

        if not captured_image:
            messages.error(request, "Please capture your face before submitting.")
            return redirect("employee_attendance", employee_id=employee.employee_id)

        try:
            image_bytes = _decode_base64_image(captured_image)
        except ValueError:
            messages.error(request, "Unable to read the captured image. Please retake and try again.")
            return redirect("employee_attendance", employee_id=employee.employee_id)

        try:
            identify_result = face_api.identify(image_bytes)
            matched_name = face_api.extract_match_name(identify_result)
        except face_api.FaceAPIError as exc:
            messages.error(request, f"Face verification failed: {exc}")
            return redirect("employee_attendance", employee_id=employee.employee_id)

        expected_names = {employee.employee_id.lower()}
        if personal and personal.full_name:
            expected_names.add(personal.full_name.lower())
        if employee.user:
            user_full_name = f"{employee.user.first_name} {employee.user.last_name}".strip()
            if user_full_name:
                expected_names.add(user_full_name.lower())

        matched_name_value = str(matched_name).strip().lower() if matched_name else ""

        if not matched_name_value or matched_name_value not in expected_names:
            messages.error(request, "Face does not match this employee. Please try again.")
            return redirect("employee_attendance", employee_id=employee.employee_id)

        confidence = (
            identify_result.get("confidence")
            or identify_result.get("score")
            or identify_result.get("similarity")
        )
        if isinstance(confidence, (int, float)):
            confidence_label = f" (confidence: {confidence:.2f})"
        elif confidence:
            confidence_label = f" (confidence: {confidence})"
        else:
            confidence_label = ""

        # Record check-in if not already set
        if action == "check_in" and attendance.check_in is None:
            attendance.check_in = now
            attendance.save()
            messages.success(request, f"Check-in recorded after face verification{confidence_label}.")

        # Record/update check-out and compute total duration
        # Allow multiple clock-outs as a failsafe (user can update if they made a mistake)
        elif action == "check_out" and attendance.check_in is not None:
            attendance.check_out = now
            attendance.total_duration = attendance.check_out - attendance.check_in
            attendance.save()
            messages.success(request, f"Check-out recorded after face verification{confidence_label}.")
        else:
            messages.info(request, "No attendance change was applied.")

        return redirect("employee_attendance", employee_id=employee.employee_id)

    # Prepare display values
    def _format_time(dt):
        if not dt:
            return "--:--"
        local_dt = timezone.localtime(dt)
        return local_dt.strftime("%I:%M %p").lstrip("0")

    check_in_display = _format_time(attendance.check_in)
    check_out_display = _format_time(attendance.check_out)

    total_hours_display = "0h 00m"
    if attendance.total_duration:
        total_seconds = int(attendance.total_duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_hours_display = f"{hours}h {minutes:02d}m"

    status_label = "Not Started"
    if attendance.check_in and not attendance.check_out:
        status_label = "In Progress"
    elif attendance.check_in and attendance.check_out:
        status_label = "Completed"

    primary_action = None
    primary_label = None
    if attendance.check_in is None:
        primary_action = "check_in"
        primary_label = "Check In"
    else:
        # Allow clock-out and re-clock-out (failsafe for mistakes)
        primary_action = "check_out"
        if attendance.check_out is None:
            primary_label = "Clock Out"
        else:
            primary_label = "Update Clock Out"

    # Simple log message for today's activity
    log_message = "No activity recorded for today yet."
    log_time_display = "--:--"
    log_status = "Idle"
    log_status_color = "text-gray-500"

    if attendance.check_out:
        log_message = "Checked out successfully."
        log_time_display = _format_time(attendance.check_out)
        log_status = "Completed"
        log_status_color = "text-emerald-600"
    elif attendance.check_in:
        log_message = "Checked in and shift in progress."
        log_time_display = _format_time(attendance.check_in)
        log_status = "In Progress"
        log_status_color = "text-orange-500"

    current_time = now.strftime("%I:%M %p").lstrip("0")
    current_date = now.strftime("%A, %b %d, %Y")

    first_name = None
    if personal and personal.full_name:
        first_name = personal.full_name.split(" ")[0]
    elif employee.user and employee.user.first_name:
        first_name = employee.user.first_name
    else:
        first_name = employee.employee_id

    context = {
        "employee": employee,
        "personal": personal,
        "attendance": attendance,
        "check_in_display": check_in_display,
        "check_out_display": check_out_display,
        "total_hours_display": total_hours_display,
        "status_label": status_label,
        "primary_action": primary_action,
        "primary_label": primary_label,
        "log_message": log_message,
        "log_time_display": log_time_display,
        "log_status": log_status,
        "log_status_color": log_status_color,
        "current_time": current_time,
        "current_date": current_date,
        "first_name": first_name,
    }
    return render(request, "employeePages/employee_attendance.html", context)


# ================= ADMIN VIEWS (Editable) =================

@login_required
@user_passes_test(is_hr_or_superuser)
def employee_general_admin_view(request, employee_id):
    """Admin view for editing employee general/personal information."""
    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)
    
    if request.method == "POST":
        # Update personal info
        if personal:
            personal.full_name = request.POST.get("full_name", personal.full_name)
            personal.gender = request.POST.get("gender", personal.gender)
            personal.date_of_birth = request.POST.get("date_of_birth", personal.date_of_birth)
            personal.email = request.POST.get("email", personal.email)
            personal.phone_number = request.POST.get("phone_number", personal.phone_number)
            personal.marital_status = request.POST.get("marital_status", personal.marital_status)
            personal.personal_id = request.POST.get("personal_id", personal.personal_id)
            personal.emergency_contact = request.POST.get("emergency_contact", personal.emergency_contact)
            personal.save()
        
        return redirect("employee_general_admin", employee_id=employee.employee_id)
    
    context = {
        "employee": employee,
        "personal": personal,
    }
    return render(request, "adminPages/employee1_admin.html", context)


@login_required
@user_passes_test(is_hr_or_superuser)
def employee_job_admin_view(request, employee_id):
    """Admin view for editing employee job information."""
    employee = _get_employee_or_404(employee_id)
    job_history = JobHistory.objects.filter(employee=employee).order_by("-effective_date")
    contracts = EmploymentContract.objects.filter(employee=employee).order_by("-start_date")
    schedule = getattr(employee, "workschedule", None)
    
    from datetime import date
    today = date.today()
    service_years = None
    if employee.join_date:
        service_years = (today - employee.join_date).days // 365
    
    if request.method == "POST":
        # Update employee profile
        employee.job_title = request.POST.get("job_title", employee.job_title)
        employee.department = request.POST.get("department", employee.department)
        employee.office = request.POST.get("office", employee.office)
        employee.employment_type = request.POST.get("employment_type", employee.employment_type)
        employee.status = request.POST.get("status", employee.status)
        
        join_date_str = request.POST.get("join_date")
        if join_date_str:
            try:
                employee.join_date = date.fromisoformat(join_date_str)
            except ValueError:
                pass
        
        employee.save()
        
        # Update work schedule
        if schedule:
            schedule.working_hours = request.POST.get("working_hours", schedule.working_hours)
            schedule.working_days = request.POST.get("working_days", schedule.working_days)
            schedule.save()
        
        return redirect("employee_job_admin", employee_id=employee.employee_id)
    
    context = {
        "employee": employee,
        "job_history": job_history,
        "contracts": contracts,
        "schedule": schedule,
        "service_years": service_years,
    }
    return render(request, "adminPages/employee2_admin.html", context)


@login_required
@user_passes_test(is_hr_or_superuser)
def employee_payroll_admin_view(request, employee_id):
    """Admin view for editing employee payroll information."""
    employee = _get_employee_or_404(employee_id)
    earnings = SalaryComponent.objects.filter(employee=employee, component_type="EARNING")
    deductions = SalaryComponent.objects.filter(employee=employee, component_type="DEDUCTION")
    bank = getattr(employee, "bankdetail", None)
    _ensure_current_month_payroll(employee)
    payroll_history = Payroll.objects.filter(employee=employee).order_by("-payment_date")
    last_pay = payroll_history.first()
    
    from django.db.models import Sum
    earnings_total = earnings.aggregate(total=Sum("amount"))["total"] or 0
    deductions_total = deductions.aggregate(total=Sum("amount"))["total"] or 0
    
    if request.method == "POST":
        # Update bank details
        if bank:
            bank.bank_name = request.POST.get("bank_name", bank.bank_name)
            bank.account_title = request.POST.get("account_title", bank.account_title)
            bank.account_number = request.POST.get("account_number", bank.account_number)
            bank.iban = request.POST.get("iban", bank.iban)
            bank.payment_frequency = request.POST.get("payment_frequency", bank.payment_frequency)
            bank.save()
        
        # Update salary components (simplified - just update existing ones)
        for earning in earnings:
            amount_key = f"earning_{earning.id}"
            if amount_key in request.POST:
                try:
                    earning.amount = float(request.POST[amount_key])
                    earning.save()
                except ValueError:
                    pass
        
        for deduction in deductions:
            amount_key = f"deduction_{deduction.id}"
            if amount_key in request.POST:
                try:
                    deduction.amount = float(request.POST[amount_key])
                    deduction.save()
                except ValueError:
                    pass
        
        # Do NOT update existing payroll records
        # Only future months will have updated values when new payslips are generated
        # This preserves historical accuracy of already-generated payslips
        
        return redirect("employee_payroll_admin", employee_id=employee.employee_id)
    
    # Calculate what the net salary will be for future payslips
    calculated_net_salary = earnings_total - deductions_total
    
    context = {
        "employee": employee,
        "earnings": earnings,
        "deductions": deductions,
        "bank": bank,
        "payroll_history": payroll_history,
        "last_pay": last_pay,
        "earnings_total": earnings_total,
        "deductions_total": deductions_total,
        "calculated_net_salary": calculated_net_salary,
    }
    return render(request, "adminPages/employee3_admin.html", context)


@login_required
@user_passes_test(is_hr_or_superuser)
def employee_documents_admin_view(request, employee_id):
    """Admin view for managing employee documents."""
    employee = _get_employee_or_404(employee_id)
    documents = EmployeeDocument.objects.filter(employee=employee).order_by("-uploaded_at")

    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        EmployeeDocument.objects.create(
            employee=employee,
            name=file.name,
            category="IDENTITY",  # Default category
            file=file,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
        return redirect("employee_documents_admin", employee_id=employee.employee_id)

    context = {
        "employee": employee,
        "documents": documents,
    }
    return render(request, "adminPages/employee4_admin.html", context)


def employee_schedule_view(request, employee_id):
    """Employee schedule page with real current dates for the week."""
    if not can_access_employee(request.user, employee_id):
        messages.error(request, "You don't have permission to access this page.")
        return redirect("login")

    from datetime import timedelta

    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)
    schedule = getattr(employee, "workschedule", None)

    today = timezone.localdate()
    now = timezone.localtime()

    # Determine current week (Monday to Sunday)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    week_range_label = f"{start_of_week.strftime('%b %d')} - {end_of_week.strftime('%b %d')}"

    default_shift_hours = "9:00 AM - 5:00 PM"
    shift_hours = schedule.working_hours if schedule and schedule.working_hours else default_shift_hours

    # Parse shift hours for today's scheduled times
    today_start = "9:00 AM"
    today_end = "5:00 PM"
    today_total_hours = "8h 00m"
    late_threshold_time = "9:15 AM"
    
    if "-" in shift_hours:
        parts = shift_hours.split("-", 1)
        today_start = parts[0].strip()
        today_end = parts[1].strip()
        
        # Calculate scheduled total hours
        try:
            from datetime import datetime
            import re
            
            # Normalize: ensure there's a space before AM/PM
            start_str = today_start.upper()
            end_str = today_end.upper()
            
            # Add space before AM/PM if missing (e.g., "10:00AM" -> "10:00 AM")
            start_str = re.sub(r'(\d)(AM|PM)', r'\1 \2', start_str)
            end_str = re.sub(r'(\d)(AM|PM)', r'\1 \2', end_str)
            
            start_time = None
            end_time = None
            
            # Try parsing with minutes first, then without
            for fmt in ["%I:%M %p", "%I %p"]:
                if start_time is None:
                    try:
                        start_time = datetime.strptime(start_str, fmt)
                    except ValueError:
                        pass
                if end_time is None:
                    try:
                        end_time = datetime.strptime(end_str, fmt)
                    except ValueError:
                        pass
            
            if start_time and end_time:
                # Handle case where end time is next day (e.g., 11 PM - 6 AM)
                if end_time < start_time:
                    end_time = end_time.replace(day=end_time.day + 1)
                
                duration = end_time - start_time
                total_seconds = duration.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                today_total_hours = f"{hours}h {minutes:02d}m"
                
                # Calculate late threshold as start time + 15 minutes
                late_threshold_dt = start_time + timedelta(minutes=15)
                late_threshold_time = late_threshold_dt.strftime("%I:%M %p").lstrip("0")
        except Exception as e:
            today_total_hours = "8h 00m"
            late_threshold_time = "9:15 AM"

    week_days = []
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        is_today = day_date == today
        weekday_short = day_date.strftime("%a").upper()
        date_label = day_date.strftime("%b %d")

        # Working day detection based on schedule working_days text or Mon-Fri default
        is_working = False
        if schedule and schedule.working_days:
            working_days_lower = schedule.working_days.lower()
            weekday_full = day_date.strftime("%A").lower()
            
            # Check for common patterns like "Monday - Friday" or individual day names
            if "monday" in working_days_lower and "friday" in working_days_lower:
                # Pattern like "Monday - Friday" means all weekdays
                is_working = day_date.weekday() < 5
            elif weekday_full in working_days_lower:
                # Individual day name found
                is_working = True
        else:
            # Default: Monday through Friday
            is_working = day_date.weekday() < 5

        week_days.append(
            {
                "weekday_short": weekday_short,
                "date_label": date_label,
                "is_today": is_today,
                "is_working": is_working,
                "shift_hours": shift_hours if is_working else None,
            }
        )

    # Fetch today's attendance record
    attendance = EmployeeAttendance.objects.filter(
        employee=employee,
        date=today,
    ).first()

    # Format attendance times
    def _format_time(dt):
        if not dt:
            return "--:--"
        local_dt = timezone.localtime(dt)
        return local_dt.strftime("%I:%M %p").lstrip("0")

    check_in_display = _format_time(attendance.check_in) if attendance else "--:--"
    check_out_display = _format_time(attendance.check_out) if attendance else "--:--"

    # Calculate total hours worked
    total_hours_display = "0h 00m"
    if attendance and attendance.total_duration:
        total_seconds = int(attendance.total_duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_hours_display = f"{hours}h {minutes:02d}m"

    # Calculate time late
    from datetime import datetime
    time_late_display = "--"
    time_late_color = "text-gray-500"
    
    if attendance and attendance.check_in:
        try:
            # Parse the late threshold time
            threshold_time_obj = datetime.strptime(late_threshold_time, "%I:%M %p")
            
            # Create threshold datetime for today
            threshold_dt = timezone.make_aware(
                datetime.combine(today, threshold_time_obj.time())
            )
            
            # Calculate difference
            if attendance.check_in > threshold_dt:
                late_seconds = int((attendance.check_in - threshold_dt).total_seconds())
                late_minutes = late_seconds // 60
                if late_minutes > 0:
                    time_late_display = f"+{late_minutes} min"
                    time_late_color = "text-red-600"
                else:
                    time_late_display = "On Time"
                    time_late_color = "text-emerald-600"
            else:
                time_late_display = "On Time"
                time_late_color = "text-emerald-600"
        except:
            time_late_display = "--"
            time_late_color = "text-gray-500"

    today_weekday = today.strftime("%A")
    today_full_date = today.strftime("%b %d, %Y")

    context = {
        "employee": employee,
        "personal": personal,
        "schedule": schedule,
        "week_days": week_days,
        "week_range_label": week_range_label,
        "shift_hours": shift_hours,
        "today_start": today_start,
        "today_end": today_end,
        "today_total_hours": today_total_hours,
        "check_in_display": check_in_display,
        "check_out_display": check_out_display,
        "total_hours_display": total_hours_display,
        "time_late_display": time_late_display,
        "time_late_color": time_late_color,
        "late_threshold": late_threshold_time,
        "today_weekday": today_weekday,
        "today_full_date": today_full_date,
        "current_date": now.strftime("%b %d, %Y"),
    }
    return render(request, "employeePages/employee_schedule.html", context)
