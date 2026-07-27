"""Dialling code on every form that takes a phone number, plus the
volunteer's preferred area.

`phone_code` is a separate column from `phone` so the code can be a validated
dropdown while rows submitted before it existed keep their single free-typed
number. Both are blank-able at the database level; the forms decide what an
applicant must actually fill in.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("submissions", "0002_embark_application_sections"),
    ]

    operations = [
        migrations.AddField(
            model_name="embarkapplication",
            name="phone_code",
            field=models.CharField(blank=True, max_length=8, verbose_name="Country code"),
        ),
        migrations.AddField(
            model_name="facultyapplication",
            name="phone_code",
            field=models.CharField(blank=True, max_length=8, verbose_name="Country code"),
        ),
        migrations.AddField(
            model_name="volunteerapplication",
            name="phone_code",
            field=models.CharField(blank=True, max_length=8, verbose_name="Country code"),
        ),
        migrations.AddField(
            model_name="partnershipinquiry",
            name="phone_code",
            field=models.CharField(blank=True, max_length=8, verbose_name="Country code"),
        ),
        migrations.AddField(
            model_name="volunteerapplication",
            name="area",
            field=models.CharField(
                blank=True, max_length=20,
                choices=[("programme", "Programme coordination"),
                         ("events", "Event management"),
                         ("marketing", "Marketing and communications"),
                         ("content", "Content creation"),
                         ("technology", "Technology"),
                         ("design", "Design"),
                         ("admin", "Administration"),
                         ("community", "Community engagement"),
                         ("other", "Other (tell us in your motivation)")],
                verbose_name="Area you want to volunteer in"),
        ),
        # Phone labels normalised so "Country code" and "Phone number" read as a pair.
        migrations.AlterField(
            model_name="facultyapplication",
            name="phone",
            field=models.CharField(max_length=32, verbose_name="Phone number"),
        ),
        migrations.AlterField(
            model_name="volunteerapplication",
            name="phone",
            field=models.CharField(max_length=32, verbose_name="Phone number"),
        ),
        migrations.AlterField(
            model_name="partnershipinquiry",
            name="phone",
            field=models.CharField(max_length=32, verbose_name="Phone number"),
        ),
    ]
