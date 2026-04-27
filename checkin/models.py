from django.db import models


class RegisteredParticipant(models.Model):
    submission_order = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    unid = models.CharField(max_length=100, unique=True)
    major = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    checked_in = models.BooleanField(default=False)
    checkin_time = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["submission_order", "id"]

    def __str__(self):
        return f"{self.name} ({self.unid})"


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
