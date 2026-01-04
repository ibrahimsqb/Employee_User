"""
URL configuration for web_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf.urls.static import static
from django.conf import settings

from core import views as core_views

urlpatterns = [
    path("", core_views.index, name="index"),
    path("admin/", admin.site.urls),

    # Employee Directory
    path(
        "employees/directory/",
        core_views.employee_directory_view,
        name="employee_directory",
    ),

    # Onboarding
    path(
        "employees/onboarding/",
        core_views.employee_onboarding_view,
        name="employee_onboarding",
    ),

    # Employee detail tabs
    path(
        "employees/<str:employee_id>/dashboard/",
        core_views.employee_dashboard_view,
        name="employee_dashboard",
    ),
    path(
        "employees/<str:employee_id>/general/",
        core_views.employee_general_view,
        name="employee_general",
    ),
    path(
        "employees/<str:employee_id>/job/",
        core_views.employee_job_view,
        name="employee_job",
    ),
    path(
        "employees/<str:employee_id>/payroll/",
        core_views.employee_payroll_view,
        name="employee_payroll",
    ),
    path(
        "employees/<str:employee_id>/payslips/",
        core_views.employee_payslip_list_view,
        name="employee_payslip_list",
    ),
    path(
        "employees/<str:employee_id>/payslips/<int:payroll_id>/",
        core_views.employee_payslip_detail_view,
        name="employee_payslip_detail",
    ),
    path(
        "employees/<str:employee_id>/documents/",
        core_views.employee_documents_view,
        name="employee_documents",
    ),
    path(
        "employees/<str:employee_id>/attendance/",
        core_views.employee_attendance_view,
        name="employee_attendance",
    ),
    path(
        "employees/<str:employee_id>/schedule/",
        core_views.employee_schedule_view,
        name="employee_schedule",
    ),
    
    # Admin views for editing (using /manage/ prefix to avoid conflict with Django admin)
    path(
        "manage/employees/<str:employee_id>/general/",
        core_views.employee_general_admin_view,
        name="employee_general_admin",
    ),
    path(
        "manage/employees/<str:employee_id>/job/",
        core_views.employee_job_admin_view,
        name="employee_job_admin",
    ),
    path(
        "manage/employees/<str:employee_id>/payroll/",
        core_views.employee_payroll_admin_view,
        name="employee_payroll_admin",
    ),
    path(
        "manage/employees/<str:employee_id>/documents/",
        core_views.employee_documents_admin_view,
        name="employee_documents_admin",
    ),
]

#Serving media files:
if settings.DEBUG:
  urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
