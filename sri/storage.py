import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class SriCertificateStorage(FileSystemStorage):
    """Almacenamiento privado de certificados SRI."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("file_permissions_mode", 0o600)
        kwargs.setdefault("directory_permissions_mode", 0o700)
        super().__init__(*args, **kwargs)

    @property
    def base_location(self):
        return settings.SRI_PRIVATE_STORAGE_ROOT

    @property
    def location(self):
        return os.path.abspath(
            self.base_location
        )

    def url(self, name):
        raise ValueError(
            "Los certificados SRI son archivos privados "
            "y no disponen de una URL pública."
        )


sri_certificate_storage = SriCertificateStorage()
