import re

from django import forms

from checkin.models import GuestParticipant, RegisteredParticipant


UNID_PATTERN = re.compile(r"^u\d{7}$", re.IGNORECASE)

DEFAULT_GUEST_MAJORS = [
    "Accounting",
    "Communication",
    "Computer Engineering",
    "Electrical Engineering",
    "Film & Media Arts",
    "Games",
    "Information Systems",
    "Psychology",
    "Urban Ecology",
    "Other",
]


class GuestCheckInForm(forms.Form):
    name = forms.CharField(max_length=255)
    unid = forms.CharField(max_length=8)
    major = forms.CharField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        major_choices = [("", "Select Major")] + [
            (major, major) for major in DEFAULT_GUEST_MAJORS
        ]
        self.fields["major"].widget = forms.Select(choices=major_choices)

        self.fields["name"].widget.attrs.update({"placeholder": "Guest full name"})
        self.fields["unid"].widget.attrs.update({"placeholder": "u1234567"})

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean_unid(self):
        normalized_unid = self.cleaned_data["unid"].strip().lower()

        if not UNID_PATTERN.match(normalized_unid):
            raise forms.ValidationError("UNID must be in the format u1234567.")

        if RegisteredParticipant.objects.filter(unid=normalized_unid).exists():
            raise forms.ValidationError(
                "This UNID is already in the registered RSVP list. Use Registered Check-In instead."
            )

        if GuestParticipant.objects.filter(unid=normalized_unid).exists():
            raise forms.ValidationError("This guest UNID has already been checked in.")

        return normalized_unid

    def clean_major(self):
        selected_major = (self.cleaned_data["major"] or "").strip()
        if selected_major in DEFAULT_GUEST_MAJORS:
            return selected_major
        return "Other"
