from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction

from core.constants.document_status import DocumentStatus

from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument
from sri.services.access_key_service import AccessKeyService
from sri.services.fiscal_sequence_service import FiscalSequenceService


class ElectronicDocumentService:
    """
    Servicio responsable de crear el documento electrónico SRI
    asociado a un documento del ERP.

    En esta fase prepara la relación entre el documento
    confirmado del ERP y su documento electrónico.

    Genera:
    - Código numérico
    - Clave de acceso SRI

    No genera XML.
    No firma.
    No envía al SRI.
    No consulta autorización.
    """

    @staticmethod
    @transaction.atomic
    def create(
        document,
        document_type,
        emission_point,
        environment,
        emission_type,
    ):

        # --------------------------------------------------
        # 1. El documento ERP debe estar confirmado
        # --------------------------------------------------

        if document.status != DocumentStatus.CONFIRMED:
            raise ValueError(
                "Solo se puede generar un documento electrónico "
                "a partir de un documento confirmado."
            )

        # --------------------------------------------------
        # 2. El documento debe tener número
        # --------------------------------------------------

        if not document.number:
            raise ValueError(
                "El documento debe tener un número antes de "
                "generar el documento electrónico."
            )

        # --------------------------------------------------
        # 3. Validar punto de emisión
        # --------------------------------------------------

        if not emission_point.is_active:
            raise ValueError(
                "El punto de emisión está inactivo."
            )

        # --------------------------------------------------
        # 4. El punto pertenece a la sucursal
        # --------------------------------------------------

        if emission_point.branch_id != document.branch_id:
            raise ValueError(
                "El punto de emisión no pertenece a la "
                "sucursal del documento."
            )

        # --------------------------------------------------
        # 5. La sucursal del punto pertenece a la empresa
        # --------------------------------------------------

        if emission_point.branch.company_id != document.company_id:
            raise ValueError(
                "El punto de emisión no pertenece a la "
                "empresa del documento."
            )

        # --------------------------------------------------
        # 6. Establecimiento
        # --------------------------------------------------

        establishment = str(
            emission_point.branch.code
        ).zfill(3)

        # --------------------------------------------------
        # 8. Tipo de contenido
        #
        # ElectronicDocument utiliza GenericForeignKey.
        # --------------------------------------------------

        content_type = ContentType.objects.get_for_model(
            document
        )

        if ElectronicDocument.objects.filter(
            content_type=content_type,
            object_id=document.pk,
        ).exists():
            raise ValueError(
                "El documento ya tiene un documento electrónico generado."
            )

        # The savepoint includes the reservation and INSERT. Translate only after
        # rollback, including when called within an outer invoice transaction.
        try:
            with transaction.atomic():
                point_code = str(emission_point.code).zfill(3)
                sequential = FiscalSequenceService.next_number(
                    company=document.company,
                    establishment=establishment,
                    emission_point=point_code,
                    document_type=document_type,
                )
                # --------------------------------------------------
                # 9. Código numérico
                # --------------------------------------------------

                numeric_code = (
                    AccessKeyService.generate_numeric_code()
                )

                # --------------------------------------------------
                # 10. Clave de acceso SRI
                # --------------------------------------------------

                access_key = AccessKeyService.generate(
                    issue_date=document.issue_date,
                    document_type=document_type,
                    ruc=document.company.person.identification,
                    environment=environment,
                    establishment=establishment,
                    emission_point=point_code,
                    sequential=sequential,
                    numeric_code=numeric_code,
                    emission_type=emission_type,
                )

                # --------------------------------------------------
                # 11. Crear documento electrónico
                # --------------------------------------------------

                electronic_document = ElectronicDocument.objects.create(
                    company=document.company,
                    branch=document.branch,
                    content_type=content_type,
                    object_id=document.pk,
                    document_type=document_type,
                    environment=environment,
                    emission_type=emission_type,
                    establishment=establishment,
                    emission_point=point_code,
                    sequential=sequential,
                    numeric_code=numeric_code,
                    access_key=access_key,
                    status=SriDocumentStatus.DRAFT,
                )

                return electronic_document
        except IntegrityError as error:
            diagnostic = getattr(error.__cause__, 'diag', None)
            if getattr(diagnostic, 'constraint_name', None) == 'unique_sri_electronic_document_origin':
                raise ValueError(
                    "El documento ya tiene un documento electrónico generado."
                ) from error
            raise
