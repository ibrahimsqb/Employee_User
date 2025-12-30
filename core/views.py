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

        # Creating an initial payroll record so the Payroll tab has data
        next_pay_date_str = data.get("next_pay_date") or None
        payment_method = data.get("payment_method") or "Bank Transfer"

        if next_pay_date_str:
            try:
                next_pay_date = date.fromisoformat(next_pay_date_str)
            except ValueError:
                next_pay_date = None

            if next_pay_date:
                from django.db.models import Sum

                earnings_total = (
                    SalaryComponent.objects.filter(
                        employee=profile, component_type="EARNING"
                    ).aggregate(total=Sum("amount"))["total"]
                    or 0
                )
                deductions_total = (
                    SalaryComponent.objects.filter(
                        employee=profile, component_type="DEDUCTION"
                    ).aggregate(total=Sum("amount"))["total"]
                    or 0
                )

                net_salary = earnings_total - deductions_total

                Payroll.objects.create(
                    employee=profile,
                    period_start=join_date or date.today(),
                    period_end=next_pay_date,
                    total_earnings=earnings_total,
                    total_deductions=deductions_total,
                    net_salary=net_salary,
                    payment_method=payment_method,
                    payment_date=next_pay_date,
                )

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
        "employeePages/employee_onboarding.html",
        {"default_employee_id": default_employee_id},
    )


def _get_employee_or_404(employee_id: str) -> EmployeeProfile:
    return get_object_or_404(EmployeeProfile, employee_id=employee_id)


def employee_general_view(request, employee_id):
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
    payroll_history = Payroll.objects.filter(employee=employee).order_by("-payment_date")

    last_pay = payroll_history.first()

    from django.db.models import Sum

    earnings_total = earnings.aggregate(total=Sum("amount"))["total"] or 0
    deductions_total = deductions.aggregate(total=Sum("amount"))["total"] or 0

    context = {
        "employee": employee,
        "earnings": earnings,
        "deductions": deductions,
        "bank": bank,
        "payroll_history": payroll_history,
        "last_pay": last_pay,
        "earnings_total": earnings_total,
        "deductions_total": deductions_total,
    }
    return render(request, "employeePages/employee3.html", context)


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