from django.db import models


class RegisteredParticipant(models.Model):
    submission_order = models.PositiveIntegerField()
    name = models.CharField(max_length=255, blank=True, default="")
    unid = models.CharField(max_length=255, unique=True)
    major = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True)
    answers = models.JSONField(default=dict, blank=True)
    checked_in = models.BooleanField(default=False)
    checkin_time = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["submission_order", "id"]

    def __str__(self):
        display_name = self.name or self.unid
        return f"{display_name} ({self.unid})"


class RSVPImportConfiguration(models.Model):
    UNIQUE_IDENTIFIER_COLUMN = "column"
    UNIQUE_IDENTIFIER_NAME_TIMESTAMP = "name_timestamp"
    UNIQUE_IDENTIFIER_INTERNAL = "internal"
    UNIQUE_IDENTIFIER_STRATEGIES = (
        (UNIQUE_IDENTIFIER_COLUMN, "Column"),
        (UNIQUE_IDENTIFIER_NAME_TIMESTAMP, "Name + Timestamp"),
        (UNIQUE_IDENTIFIER_INTERNAL, "Generate Internal RSVP ID"),
    )

    imported_columns = models.JSONField(default=list, blank=True)
    display_columns = models.JSONField(default=list, blank=True)
    searchable_columns = models.JSONField(default=list, blank=True)
    unique_identifier_strategy = models.CharField(
        max_length=32,
        choices=UNIQUE_IDENTIFIER_STRATEGIES,
        default=UNIQUE_IDENTIFIER_COLUMN,
    )
    unique_identifier_source = models.CharField(max_length=255, blank=True)
    name_column = models.CharField(max_length=255, blank=True)
    major_column = models.CharField(max_length=255, blank=True)
    email_column = models.CharField(max_length=255, blank=True)
    timestamp_column = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "RSVP import configuration"
        verbose_name_plural = "RSVP import configurations"

    def __str__(self):
        return "RSVP Import Configuration"


class GuestParticipant(models.Model):
    name = models.CharField(max_length=255)
    unid = models.CharField(max_length=100, blank=True)
    major = models.CharField(max_length=255, blank=True)
    checked_in = models.BooleanField(default=True)
    checkin_time = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checkin_time", "-created_at", "id"]

    def __str__(self):
        return self.name
