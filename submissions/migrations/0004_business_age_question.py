"""Reword the business-age question on the Embark application.

Label only — the column still stores the four-digit year the business was
established, which is why the old wording survives as the field's help text.
No schema change; this migration exists so makemigrations stays quiet.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("submissions", "0003_phone_code_and_volunteer_area"),
    ]

    operations = [
        migrations.AlterField(
            model_name="embarkapplication",
            name="year_established",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                help_text="Year the business was established.",
                verbose_name="How old is the business?"),
        ),
    ]
