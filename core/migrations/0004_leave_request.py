# Generated manually to add LeaveRequest model
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_employeeattendance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LeaveRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('leave_type', models.CharField(choices=[('ANNUAL', 'Annual'), ('MEDICAL', 'Medical'), ('CASUAL', 'Casual')], max_length=20)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('applied_date', models.DateField(default=django.utils.timezone.localdate)),
                ('days', models.PositiveIntegerField(default=0)),
                ('reason', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('APPLIED', 'Applied'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], default='APPLIED', max_length=20)),
                ('decision_date', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_leaves', to=settings.AUTH_USER_MODEL)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leave_requests', to='core.employeeprofile')),
            ],
            options={'ordering': ['-applied_date', '-created_at']},
        ),
    ]
