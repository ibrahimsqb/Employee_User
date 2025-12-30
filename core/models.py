from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.

class EmployeeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    employee_id = models.CharField(max_length=20, unique=True)

    department = models.CharField(
        max_length=30,
        choices=[
            ('ENGINEERING', 'Engineering'),
            ('PROCUREMENT', 'Procurement'),
            ('FINANCE', 'Finance'),
            ('CONSTRUCTION', 'Construction'),
            ('HSE', 'HSE'),
        ]
    )

    job_title = models.CharField(max_length=100)
    office = models.CharField(max_length=100, blank=True)

    employment_type = models.CharField(
        max_length=20,
        choices=[
            ('FULL_TIME', 'Full Time'),
            ('PART_TIME', 'Part Time'),
            ('CONTRACT', 'Contract'),
        ] 
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('ACTIVE', 'Active'),
            ('INACTIVE', 'Inactive'),
            ('TERMINATED', 'Terminated'),
        ],
        default='ACTIVE'
    )

    join_date = models.DateField()
    exit_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

class EmployeePersonalInfo(models.Model):
    employee = models.OneToOneField(EmployeeProfile, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=150)
    gender = models.CharField(
        max_length=10,
        choices=[('MALE','Male'), ('FEMALE','Female'), ('OTHER','Other')]
    )

    date_of_birth = models.DateField()
    marital_status = models.CharField(max_length=20)

    email = models.EmailField()
    phone_number = models.CharField(max_length=20)

    personal_id = models.CharField(max_length=50)  # CNIC / Passport
    emergency_contact = models.CharField(max_length=20)

    timezone = models.CharField(max_length=50, default='UTC+5')

class EmployeeOnboarding(models.Model):
    employee = models.OneToOneField(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="onboarding"
    )

    # Onboarding status
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    # Manager during onboarding
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='onboarded_employees'
    )

    joining_date = models.DateField()

    # Orientation checklist
    welcome_session_completed = models.BooleanField(default=False)
    safety_training_completed = models.BooleanField(default=False)
    culture_training_completed = models.BooleanField(default=False)

    notes = models.TextField(blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

class JobHistory(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE)

    effective_date = models.DateField()
    job_title = models.CharField(max_length=100)
    position_type = models.CharField(max_length=50)
    employment_type = models.CharField(max_length=20)
    line_manager = models.CharField(max_length=50, default="Not Assigned")
    # line_manager = models.ForeignKey(
    #     User, on_delete=models.SET_NULL, null=True, related_name='managed_employees'
    # )

    created_at = models.DateTimeField(auto_now_add=True)

class EmploymentContract(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE)

    contract_number = models.CharField(max_length=50)
    contract_name = models.CharField(max_length=100)
    contract_type = models.CharField(max_length=50)

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

class WorkSchedule(models.Model):
    employee = models.OneToOneField(EmployeeProfile, on_delete=models.CASCADE)

    working_hours = models.CharField(max_length=50)   # "9:00am – 5:00pm"
    working_days = models.CharField(max_length=100)   # "Mon – Fri"

class SalaryComponent(models.Model):
    COMPONENT_TYPE = [
        ('EARNING', 'Earning'),
        ('DEDUCTION', 'Deduction'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    component_type = models.CharField(max_length=10, choices=COMPONENT_TYPE)

class Payroll(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE)

    period_start = models.DateField()
    period_end = models.DateField()

    total_earnings = models.DecimalField(max_digits=10, decimal_places=2)
    total_deductions = models.DecimalField(max_digits=10, decimal_places=2)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2)

    payment_method = models.CharField(max_length=50)
    payment_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

class BankDetail(models.Model):
    employee = models.OneToOneField(EmployeeProfile, on_delete=models.CASCADE)

    bank_name = models.CharField(max_length=100)
    account_title = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    iban = models.CharField(max_length=50)

    payment_frequency = models.CharField(
        max_length=20,
        choices=[('MONTHLY','Monthly'), ('WEEKLY','Weekly')]
    )

class EmployeeDocument(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE)

    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=50,
        choices=[
            ('IDENTITY','Identity'),
            ('EMPLOYMENT','Employment'),
            ('CONTRACT','Contract'),
            ('CERTIFICATION','Certification'),
        ]
    )

    file = models.FileField(upload_to='employee_documents/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class RequiredDocument(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE)

    name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=[
            ('UPLOADED','Uploaded'),
            ('PENDING','Pending'),
            ('MISSING','Missing'),
        ]
    )










