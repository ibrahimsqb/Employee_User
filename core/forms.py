from django import forms
from django.contrib.auth.models import User

from .models import (
    EmployeeProfile,
    EmployeePersonalInfo,
    EmployeeOnboarding,
    JobHistory,
    EmploymentContract,
    WorkSchedule,
    BankDetail,
    EmployeeDocument,
    SalaryComponent,
)


class EmployeeUserForm(forms.ModelForm):
    """Handles creation of the auth user for the employee."""

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]


class EmployeeProfileForm(forms.ModelForm):
    class Meta:
        model = EmployeeProfile
        fields = [
            "employee_id",
            "department",
            "job_title",
            "office",
            "employment_type",
            "status",
            "join_date",
            "exit_date",
        ]
        widgets = {
            "join_date": forms.DateInput(attrs={"type": "date"}),
            "exit_date": forms.DateInput(attrs={"type": "date"}),
        }


class EmployeePersonalInfoForm(forms.ModelForm):
    class Meta:
        model = EmployeePersonalInfo
        fields = [
            "full_name",
            "gender",
            "date_of_birth",
            "marital_status",
            "email",
            "phone_number",
            "personal_id",
            "emergency_contact",
            "timezone",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }


class EmployeeOnboardingForm(forms.ModelForm):
    class Meta:
        model = EmployeeOnboarding
        fields = [
            "status",
            "manager",
            "joining_date",
            "welcome_session_completed",
            "safety_training_completed",
            "culture_training_completed",
            "notes",
        ]
        widgets = {
            "joining_date": forms.DateInput(attrs={"type": "date"}),
        }


class JobHistoryForm(forms.ModelForm):
    class Meta:
        model = JobHistory
        fields = [
            "effective_date",
            "job_title",
            "position_type",
            "employment_type",
            "line_manager",
        ]
        widgets = {
            "effective_date": forms.DateInput(attrs={"type": "date"}),
        }


class EmploymentContractForm(forms.ModelForm):
    class Meta:
        model = EmploymentContract
        fields = [
            "contract_number",
            "contract_name",
            "contract_type",
            "start_date",
            "end_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class WorkScheduleForm(forms.ModelForm):
    class Meta:
        model = WorkSchedule
        fields = ["working_hours", "working_days"]


class BankDetailForm(forms.ModelForm):
    class Meta:
        model = BankDetail
        fields = [
            "bank_name",
            "account_title",
            "account_number",
            "iban",
            "payment_frequency",
        ]


class EmployeeDocumentForm(forms.ModelForm):
    """Simple upload form; name/category are set in the view."""

    class Meta:
        model = EmployeeDocument
        fields = ["file"]


class EarningComponentForm(forms.ModelForm):
    class Meta:
        model = SalaryComponent
        fields = ["name", "amount"]

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.component_type = "EARNING"
        if commit:
            instance.save()
        return instance


class DeductionComponentForm(forms.ModelForm):
    class Meta:
        model = SalaryComponent
        fields = ["name", "amount"]

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.component_type = "DEDUCTION"
        if commit:
            instance.save()
        return instance
