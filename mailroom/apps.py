from django.apps import AppConfig


class MailroomConfig(AppConfig):
    """The staff mailbox: mail the team writes, and mail people send back."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "mailroom"
    verbose_name = "Staff email"
