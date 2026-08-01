"""Applicants link their video instead of uploading it.

The 10 GB droplet cannot hold 64 MB per applicant: roughly seventy applications
would fill the disk, and a full disk stops SQLite writing at all — the site
would start refusing every form, not just the video. Section B now asks for a
Google Drive link.

`business_video` is kept rather than dropped. Applications submitted before this
migration hold real files the team still needs, and the staff-only download view
and ZIP action still serve them. The column moves to the collapsed legacy
section of the admin; nothing new is ever written to it.
"""
from django.db import migrations, models

import submissions.models


class Migration(migrations.Migration):

    dependencies = [
        ("submissions", "0004_business_age_question"),
    ]

    operations = [
        migrations.AddField(
            model_name="embarkapplication",
            name="business_video_url",
            field=models.URLField(
                blank=True, max_length=500,
                help_text="Upload the clip to Google Drive, then set sharing to “Anyone "
                          "with the link” and paste that link here. An unlisted YouTube, "
                          "Vimeo or Dropbox link works too. A private link cannot be "
                          "reviewed.",
                verbose_name="Link to your one-minute business video"),
        ),
        migrations.AlterField(
            model_name="embarkapplication",
            name="business_video",
            field=models.FileField(
                blank=True, upload_to="applications/videos/",
                validators=[submissions.models.validate_application_video],
                help_text="Legacy — superseded by the video link.",
                verbose_name="One-minute business video (uploaded, pre-2026-08)"),
        ),
    ]
