from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from checkin.models import GuestParticipant, RegisteredParticipant
from checkin.services.import_rsvp import import_rsvp_file


class RSVPImportServiceTests(TestCase):
    def test_imports_valid_rows_and_skips_duplicates_and_missing_values(self):
        RegisteredParticipant.objects.create(
            submission_order=1,
            name="Existing Student",
            unid="u1000",
            major="Economics",
        )

        csv_content = "\n".join(
            [
                "Name,UNID,Major",
                "Alice,u1001,Computer Science",
                "Bob,u1000,Mathematics",
                "Carol,,History",
                "Dan,u1002,Physics",
                "Erin,u1002,Chemistry",
            ]
        )

        uploaded_file = SimpleUploadedFile(
            "rsvp.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        summary = import_rsvp_file(uploaded_file)

        self.assertEqual(summary["imported_count"], 2)
        self.assertEqual(summary["skipped_count"], 3)
        self.assertEqual(summary["duplicate_unids"], ["u1000", "u1002"])
        self.assertEqual(
            list(
                RegisteredParticipant.objects.order_by("submission_order").values_list(
                    "name", "submission_order"
                )
            ),
            [
                ("Existing Student", 1),
                ("Alice", 2),
                ("Dan", 3),
            ],
        )

    def test_reports_missing_required_headers(self):
        uploaded_file = SimpleUploadedFile(
            "rsvp.csv",
            b"Name,Email\nAlice,alice@example.com\n",
            content_type="text/csv",
        )

        summary = import_rsvp_file(uploaded_file)

        self.assertEqual(summary["imported_count"], 0)
        self.assertIn("Missing required column(s)", summary["errors"][0])


class AttendanceExportViewTests(TestCase):
    def test_export_includes_checked_in_registered_and_all_guests(self):
        RegisteredParticipant.objects.create(
            submission_order=1,
            name="Checked In Student",
            unid="u2000",
            major="Biology",
            checked_in=True,
        )
        RegisteredParticipant.objects.create(
            submission_order=2,
            name="Not Checked In Student",
            unid="u2001",
            major="Physics",
            checked_in=False,
        )
        GuestParticipant.objects.create(
            name="Walk-in Guest",
            unid="g3000",
            major="Visitor",
        )

        response = self.client.get("/checkin/export/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode("utf-8")
        self.assertIn("Registered,Checked In Student,u2000,Biology,Yes,", content)
        self.assertNotIn("Not Checked In Student", content)
        self.assertIn("Guest,Walk-in Guest,g3000,Visitor,Yes,", content)


class ImportPageParticipantListTests(TestCase):
    def test_import_page_shows_registered_participants_in_submission_order(self):
        RegisteredParticipant.objects.create(
            submission_order=2,
            name="Second Student",
            unid="u3002",
            major="Finance",
        )
        RegisteredParticipant.objects.create(
            submission_order=1,
            name="First Student",
            unid="u3001",
            major="Marketing",
            checked_in=True,
        )

        response = self.client.get("/checkin/import/")

        self.assertEqual(response.status_code, 200)
        participants = list(response.context["participants"])
        self.assertEqual(
            [participant.name for participant in participants],
            ["First Student", "Second Student"],
        )
        self.assertContains(response, "Imported RSVP Participants")

    def test_toggle_checkin_updates_status_and_time(self):
        participant = RegisteredParticipant.objects.create(
            submission_order=1,
            name="Toggle Student",
            unid="u4001",
            major="Operations",
            checked_in=False,
            checkin_time=None,
        )

        response = self.client.post(f"/checkin/participants/{participant.id}/toggle-checkin/")

        participant.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(participant.checked_in)
        self.assertIsNotNone(participant.checkin_time)

        previous_checkin_time = participant.checkin_time
        response = self.client.post(f"/checkin/participants/{participant.id}/toggle-checkin/")

        participant.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(participant.checked_in)
        self.assertIsNone(participant.checkin_time)
        self.assertIsNotNone(previous_checkin_time)
