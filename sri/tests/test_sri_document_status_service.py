from django.test import TestCase

from sri.constants.document_status import SriDocumentStatus
from sri.services.sri_document_status_service import (
    SriDocumentStatusService,
)


class SriDocumentStatusServiceTest(TestCase):


    def test_draft_to_generated(self):

        self.assertIn(
            SriDocumentStatus.GENERATED,
            SriDocumentStatusService.ALLOWED_TRANSITIONS[
                SriDocumentStatus.DRAFT
            ]
        )


    def test_generated_to_signed(self):

        self.assertIn(
            SriDocumentStatus.SIGNED,
            SriDocumentStatusService.ALLOWED_TRANSITIONS[
                SriDocumentStatus.GENERATED
            ]
        )


    def test_invalid_transition(self):

        self.assertNotIn(
            SriDocumentStatus.AUTHORIZED,
            SriDocumentStatusService.ALLOWED_TRANSITIONS[
                SriDocumentStatus.DRAFT
            ]
        )
