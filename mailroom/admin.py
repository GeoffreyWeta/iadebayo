"""Read-only views for a superuser debugging the mailbox. Staff use /staff/mail/."""
from django.contrib import admin

from .models import Attachment, Conversation, Message


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class MessageInline(admin.TabularInline):
    model = Message
    fields = ("direction", "sent_at", "from_email", "to", "subject", "message_id")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True


@admin.register(Conversation)
class ConversationAdmin(ReadOnly):
    list_display = ("subject", "contact_email", "mailbox", "last_message_at",
                    "unread", "archived", "junk")
    list_filter = ("unread", "archived", "junk", "mailbox")
    search_fields = ("subject", "contact_email", "participants")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(ReadOnly):
    list_display = ("subject", "direction", "from_email", "sent_at", "auth_results")
    list_filter = ("direction", "suspicious")
    search_fields = ("subject", "from_email", "to", "message_id")


@admin.register(Attachment)
class AttachmentAdmin(ReadOnly):
    list_display = ("filename", "content_type", "size", "message")
