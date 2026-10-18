"""Central structural validation; never certifies existence/status at the SRI."""
import re
import unicodedata
from django.core.exceptions import ValidationError

FINAL_CONSUMER_ID = '9999999999999'


def invalid(message, code='invalid_identification'):
    raise ValidationError({'identification': ValidationError(message, code=code)})


def validate_cedula(value):
    if not re.fullmatch(r'[0-9]{10}', value):
        invalid('La Cédula debe contener exactamente 10 dígitos.', 'invalid_cedula')
    if not 1 <= int(value[:2]) <= 24 or int(value[2]) > 5:
        invalid('La estructura de la Cédula no es válida.', 'invalid_cedula')
    total = 0
    for index, digit in enumerate(value[:9]):
        weighted = int(digit) * (2 if index % 2 == 0 else 1)
        total += weighted - 9 if weighted > 9 else weighted
    if (10 - total % 10) % 10 != int(value[-1]):
        invalid('El dígito verificador de la Cédula no es válido.', 'invalid_cedula')


def validate_ruc(value):
    if not re.fullmatch(r'[0-9]{13}', value) or value == FINAL_CONSUMER_ID:
        invalid('El RUC debe contener 13 dígitos y no ser Consumidor Final.', 'invalid_ruc')
    if not 1 <= int(value[:2]) <= 24 or value[-3:] != '001':
        invalid('La estructura del RUC no es válida (provincia y terminación 001).', 'invalid_ruc')
    if int(value[2]) <= 5:
        validate_cedula(value[:10])
    elif value[2] not in '69':
        invalid('La clase de RUC no es válida.', 'invalid_ruc')
    # Assigned society/foreign RUCs: no universal modulo-11 checksum.


def detect_identification(value, manual=None):
    if not isinstance(value, str) or not value or len(value) > 20:
        invalid('Ingrese una identificación de entre 1 y 20 caracteres.')
    if value != value.strip() or any(unicodedata.category(c).startswith('C') for c in value):
        invalid('La identificación no admite espacios extremos ni caracteres de control.')
    if not any(c.isalnum() for c in value):
        invalid('La identificación debe contener letras o números.')
    if any(c.isdigit() and c not in '0123456789' for c in value):
        invalid('Utilice dígitos del 0 al 9.')
    if manual not in (None, '', 'CEDULA', 'RUC', 'PASSPORT', 'FOREIGN_ID', 'OTHER', 'FINAL_CONSUMER'):
        raise ValidationError({'identification_type': ValidationError('Tipo de identificación desconocido.', code='invalid_type')})
    if value == FINAL_CONSUMER_ID:
        return 'FINAL_CONSUMER'
    if re.fullmatch(r'[0-9]{10}', value):
        validate_cedula(value)
        return 'CEDULA'
    if re.fullmatch(r'[0-9]{13}', value):
        validate_ruc(value)
        return 'RUC'
    if manual in ('CEDULA', 'RUC'):
        invalid('La identificación no corresponde al tipo indicado.')
    return 'PASSPORT' if manual == 'PASSPORT' else 'OTHER'
