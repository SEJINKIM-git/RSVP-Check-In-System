import re

from django import forms

from checkin.models import GuestParticipant, RegisteredParticipant


UNID_PATTERN = re.compile(r"^u\d{7}$", re.IGNORECASE)

DEFAULT_GUEST_MAJORS = [
    "Accounting",
    "Business",
    "Computer Science",
    "Data Science",
    "Economics",
    "Engineering",
    "Finance",
    "Marketing",
    "Mathematics",
    "Other",
]


class GuestCheckInForm(forms.Form):
    name = forms.CharField(max_length=255)
    unid = forms.CharField(max_length=8)
    major = forms.ChoiceField(choices=())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        imported_majors = []
        for major in RegisteredParticipant.objects.order_by("major").values_list("major", flat=True).distinct():
            cleaned_major = (major or "").strip()
            if cleaned_major and cleaned_major not in imported_majors:
                imported_majors.append(cleaned_major)

        major_options = imported_majors or list(DEFAULT_GUEST_MAJORS)
        if "Other" not in major_options:
            major_options.append("Other")

        self.fields["major"].choices = [("", "Select Major")] + [
            (major, major) for major in major_options
        ]

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
