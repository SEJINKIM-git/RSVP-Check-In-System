from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from checkin.models import GuestParticipant, RegisteredParticipant
from checkin.services.import_rsvp import import_rsvp_file


class RSVPImportServiceTests(TestCase):
    def test_imports_valid_rows_and_skips_duplicates_and_missing_values(self):
        RegisteredParticipant.objects.create(
            submission_order=1,
            name="Existing Student",
            unid="u1000000",
            major="Economics",
        )

        csv_content = "\n".join(
            [
                "Name,UNID,Major",
                "Alice,u1000001,Computer Science",
                "Bob,U1000000,Mathematics",
                "Carol,,History",
                "Dan,U1000002,Physics",
                "Erin,u1000002,Chemistry",
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
        self.assertEqual(summary["duplicate_unids"], ["u1000000", "u1000002"])
        self.assertEqual(
            list(
                RegisteredParticipant.objects.order_by("submission_order").values_list(
                    "name", "submission_order", "unid"
                )
            ),
            [
                ("Existing Student", 1, "u1000000"),
                ("Alice", 2, "u1000001"),
                ("Dan", 3, "u1000002"),
            ],
        )

    def test_skips_unids_that_do_not_match_required_format_and_reports_error(self):
        csv_content = "\n".join(
            [
                "Name,UNID,Major",
                "Alice,1234567,Computer Science",
                "Bob,u123,Economics",
                "Carol,u123456,Marketing",
                "Dan,u12345678,Finance",
                "Erin,uabcdefg,Biology",
                "Frank,u1234abc,Physics",
                "Grace,U7654321,Chemistry",
            ]
        )

        uploaded_file = SimpleUploadedFile(
            "rsvp.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        summary = import_rsvp_file(uploaded_file)

        self.assertEqual(summary["imported_count"], 1)
        self.assertEqual(summary["skipped_count"], 6)
        self.assertIn("Row 2 skipped: UNID must be in the format u1234567.", summary["errors"])
        self.assertIn("Row 3 skipped: UNID must be in the format u1234567.", summary["errors"])
        self.assertIn("Row 4 skipped: UNID must be in the format u1234567.", summary["errors"])
        self.assertIn("Row 5 skipped: UNID must be in the format u1234567.", summary["errors"])
        self.assertIn("Row 6 skipped: UNID must be in the format u1234567.", summary["errors"])
        self.assertIn("Row 7 skipped: UNID must be in the format u1234567.", summary["errors"])
        participant = RegisteredParticipant.objects.get()
        self.assertEqual(participant.unid, "u7654321")

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

    def test_rsvp_export_includes_all_registered_participants(self):
        RegisteredParticipant.objects.create(
            submission_order=1,
            name="First Student",
            unid="u2100",
            major="Biology",
            checked_in=True,
        )
        RegisteredParticipant.objects.create(
            submission_order=2,
            name="Second Student",
            unid="u2101",
            major="Physics",
            checked_in=False,
        )

        response = self.client.get("/checkin/export-rsvp/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode("utf-8")
        self.assertIn("Submission Order,Name,UNID,Major,Checked In,Check-in Time", content)
        self.assertIn("1,First Student,u2100,Biology,Yes,", content)
        self.assertIn("2,Second Student,u2101,Physics,No,", content)


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

    def test_delete_participant_removes_row_and_reorders_following_rows(self):
        first = RegisteredParticipant.objects.create(
            submission_order=1,
            name="First Student",
            unid="u5001",
            major="Finance",
        )
        second = RegisteredParticipant.objects.create(
            submission_order=2,
            name="Second Student",
            unid="u5002",
            major="Marketing",
        )
        third = RegisteredParticipant.objects.create(
            submission_order=3,
            name="Third Student",
            unid="u5003",
            major="Operations",
        )

        response = self.client.post(f"/checkin/participants/{second.id}/delete/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(RegisteredParticipant.objects.filter(id=first.id).exists())
        self.assertFalse(RegisteredParticipant.objects.filter(id=second.id).exists())
        third.refresh_from_db()
        self.assertEqual(third.submission_order, 2)

    def test_delete_all_participants_clears_rsvp_list(self):
        RegisteredParticipant.objects.create(
            submission_order=1,
            name="First Student",
            unid="u6001",
            major="Accounting",
        )
        RegisteredParticipant.objects.create(
            submission_order=2,
            name="Second Student",
            unid="u6002",
            major="Finance",
        )

        response = self.client.post("/checkin/participants/delete-all/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(RegisteredParticipant.objects.count(), 0)

    def test_import_page_shows_export_and_bulk_delete_actions(self):
        RegisteredParticipant.objects.create(
            submission_order=1,
            name="Action Student",
            unid="u7001",
            major="Accounting",
        )

        response = self.client.get("/checkin/import/")

        self.assertContains(response, "Export RSVP List (CSV)")
        self.assertContains(response, "Export Final Attendance (CSV)")
        self.assertContains(response, "Delete Entire RSVP List")
        self.assertContains(response, "/checkin/participants/delete-all/")
        self.assertNotContains(response, "<th class=\"actions-cell\">Delete</th>", html=False)

    def test_import_page_shows_combined_search_input(self):
        RegisteredParticipant.objects.create(
            submission_order=1,
            name="Search Student",
            unid="u8001",
            major="Accounting",
        )

        response = self.client.get("/checkin/import/")

        self.assertContains(response, "Search by Name or UNID")
        self.assertContains(response, 'id="participant-search"', html=False)
        self.assertContains(response, "Type a name or UNID")
