"""Rebuild EmbarkApplication as the three-section form.

Adds Section A/B/Commitment fields, relaxes the four original required columns
so applications submitted against the 2025 form stay valid, and remaps the
'student' academic status to 'undergraduate'.
"""
from django.db import migrations, models

import submissions.models


def status_student_to_undergraduate(apps, schema_editor):
    apps.get_model("submissions", "EmbarkApplication").objects.filter(
        applicant_status="student").update(applicant_status="undergraduate")


def status_undergraduate_to_student(apps, schema_editor):
    apps.get_model("submissions", "EmbarkApplication").objects.filter(
        applicant_status="undergraduate").update(applicant_status="student")


class Migration(migrations.Migration):

    dependencies = [
        ("submissions", "0001_initial"),
    ]

    operations = [
        # ------------------------------------------------ Section A additions
        migrations.AddField(
            model_name="embarkapplication",
            name="gender",
            field=models.CharField(blank=True, choices=[("male", "Male"), ("female", "Female")], max_length=10),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True, verbose_name="Date of birth"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="state",
            field=models.CharField(blank=True, max_length=80, verbose_name="State / region"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="social_handle",
            field=models.CharField(blank=True, max_length=160,
                                   verbose_name="Business or personal social media handle"),
        ),
        # ------------------------------------------------ Section B additions
        migrations.AddField(
            model_name="embarkapplication",
            name="business_video",
            field=models.FileField(
                blank=True, upload_to="applications/videos/",
                help_text="Up to one minute: what your business does, the problem it solves, "
                          "and its impact or value proposition.",
                validators=[submissions.models.validate_application_video],
                verbose_name="One-minute business video"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="year_established",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Year the business was established"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="revenue_last_year",
            field=models.CharField(blank=True, max_length=80,
                                   verbose_name="Approximate revenue generated last year"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="revenue_this_year",
            field=models.CharField(blank=True, max_length=80,
                                   verbose_name="Approximate revenue generated this year"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="major_challenge",
            field=models.TextField(
                blank=True,
                verbose_name="A major challenge your business has faced, and how you addressed it"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="growth_limits",
            field=models.CharField(
                blank=True, max_length=200,
                help_text="Stored as comma-separated codes; set by the application form.",
                verbose_name="Biggest factors limiting your growth right now"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="growth_limits_other",
            field=models.CharField(blank=True, max_length=160, verbose_name="Other limiting factor"),
        ),
        # ----------------------------------------------- Commitment additions
        migrations.AddField(
            model_name="embarkapplication",
            name="device",
            field=models.CharField(
                blank=True, max_length=20,
                choices=[("laptop", "Laptop"), ("smartphone", "Smartphone"),
                         ("tablet", "Tablet"), ("desktop", "Desktop Computer")],
                verbose_name="Device you will use for the programme"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="will_participate",
            field=models.CharField(
                blank=True, max_length=3, choices=[("yes", "Yes"), ("no", "No")],
                verbose_name="Willing to participate actively throughout"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="reliable_internet",
            field=models.CharField(
                blank=True, max_length=10,
                choices=[("yes", "Yes"), ("no", "No"), ("sometimes", "Sometimes")],
                verbose_name="Reliable internet for live sessions"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="heard_about",
            field=models.CharField(
                blank=True, max_length=20,
                choices=[("linkedin", "LinkedIn"), ("instagram", "Instagram"),
                         ("facebook", "Facebook"), ("referral", "Friend/Referral"),
                         ("other", "Other (please specify)")],
                verbose_name="How they heard about Embark"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="heard_about_other",
            field=models.CharField(blank=True, max_length=160,
                                   verbose_name="Where else they heard about us"),
        ),
        migrations.AddField(
            model_name="embarkapplication",
            name="media_consent",
            field=models.BooleanField(
                default=False,
                help_text="Agreed that photos and video recorded during the programme may be "
                          "used by the Foundation.",
                verbose_name="Media release consent"),
        ),
        # --------------------------------------------- Reworked existing cols
        migrations.AlterField(
            model_name="embarkapplication",
            name="name",
            field=models.CharField(max_length=120, verbose_name="Full name"),
        ),
        migrations.AlterField(
            model_name="embarkapplication",
            name="email",
            field=models.EmailField(help_text="A Gmail address is preferred", max_length=254,
                                    verbose_name="Email address"),
        ),
        migrations.AlterField(
            model_name="embarkapplication",
            name="phone",
            field=models.CharField(max_length=32, verbose_name="Phone number"),
        ),
        migrations.AlterField(
            model_name="embarkapplication",
            name="applicant_status",
            field=models.CharField(
                blank=True, max_length=20,
                choices=[("undergraduate", "Undergraduate"), ("graduate", "Graduate")],
                verbose_name="Academic status"),
        ),
        migrations.AlterField(
            model_name="embarkapplication",
            name="institution",
            field=models.CharField(blank=True, max_length=160,
                                   help_text="Graduated from / currently attending",
                                   verbose_name="Name of institution"),
        ),
        migrations.AlterField(
            model_name="embarkapplication",
            name="business_description",
            field=models.TextField(blank=True, help_text="Legacy — superseded by the video"),
        ),
        migrations.AlterField(
            model_name="embarkapplication",
            name="business_sector",
            field=models.CharField(blank=True, help_text="Legacy", max_length=120),
        ),
        migrations.AlterField(
            model_name="embarkapplication",
            name="motivation",
            field=models.TextField(blank=True, help_text="Legacy",
                                   verbose_name="Why do you want to join Embark?"),
        ),
        # -------------------------------------------------- Data: status codes
        migrations.RunPython(status_student_to_undergraduate, status_undergraduate_to_student),
    ]
