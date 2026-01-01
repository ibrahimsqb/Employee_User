from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BankDetailForm, EmployeeDocumentForm
from .models import (
    BankDetail,
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


def index(request):
    return render(request, "core/index.html")


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
def employee_onboarding_view(request):
    """Create a new employee and all related records from the onboarding form."""

    if request.method == "POST":
        data = request.POST

        full_name = (data.get("full_name") or "").strip() or "New Employee"
        email = data.get("email") or ""
        employee_id = data.get("employee_id") or _generate_next_employee_id()
        username = employee_id or email or full_name.replace(" ", "_")

        user = User.objects.create(username=username)
        if email:
            user.email = email
        first, *rest = full_name.split(" ", 1)
        user.first_name = first
        user.last_name = rest[0] if rest else ""
        user.save()

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

        # Redirect to the General tab for the new employee
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
    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)

    context = {
        "employee": employee,
        "personal": personal,
    }
    return render(request, "employeePages/employee_dashboard.html", context)


def employee_general_view(request, employee_id):
    """Display employee general/personal information."""
    employee = _get_employee_or_404(employee_id)
    personal = getattr(employee, "employeepersonalinfo", None)
    context = {
        "employee": employee,
        "personal": personal,
    }
    return render(request, "employeePages/employee1.html", context)


def employee_job_view(request, employee_id):
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


# ================= ADMIN VIEWS (Editable) =================

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
