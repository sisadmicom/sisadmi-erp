"""Identity is immutable; new rows require a coherent catalog classification."""
from django.db import migrations

FORWARD_SQL = r"""
CREATE FUNCTION public.sisadmi_person_identity_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.identification = '9999999999999' THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                CONSTRAINT = 'people_person_reserved_protected',
                MESSAGE = 'La Persona reservada es administrada exclusivamente por el sistema.';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.identification IS DISTINCT FROM NEW.identification
       OR OLD.identification_type IS DISTINCT FROM NEW.identification_type
       OR OLD.identification_kind_id IS DISTINCT FROM NEW.identification_kind_id THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            CONSTRAINT = 'people_person_identity_immutable',
            MESSAGE = 'La identificacion y su clasificacion son inmutables.';
    END IF;
    IF OLD.identification = '9999999999999' AND OLD IS DISTINCT FROM NEW THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            CONSTRAINT = 'people_person_reserved_protected',
            MESSAGE = 'La Persona reservada es administrada exclusivamente por el sistema.';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER people_person_identity_immutable
BEFORE UPDATE OR DELETE ON public.people_person
FOR EACH ROW EXECUTE FUNCTION public.sisadmi_person_identity_guard();

CREATE FUNCTION public.sisadmi_person_identity_insert_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.identification_type IS NULL OR NEW.identification_kind_id IS NULL
       OR NOT EXISTS (SELECT 1 FROM public.people_identificationkind k
                      WHERE k.id = NEW.identification_kind_id AND k.code = NEW.identification_type) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            CONSTRAINT = 'people_person_identity_coherent',
            MESSAGE = 'El tipo y el catalogo de identificacion deben ser coherentes.';
    END IF;
    IF (NEW.identification = '9999999999999') IS DISTINCT FROM (NEW.identification_type = 'FINAL_CONSUMER') THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            CONSTRAINT = 'people_person_identity_coherent',
            MESSAGE = 'La clasificacion de la identidad reservada no es coherente.';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER people_person_identity_coherent
BEFORE INSERT ON public.people_person
FOR EACH ROW EXECUTE FUNCTION public.sisadmi_person_identity_insert_guard();

CREATE FUNCTION public.sisadmi_identification_kind_code_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.code IS DISTINCT FROM NEW.code THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            CONSTRAINT = 'people_identification_kind_code_immutable',
            MESSAGE = 'El codigo del tipo de identificacion es inmutable.';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER people_identification_kind_code_immutable
BEFORE UPDATE ON public.people_identificationkind
FOR EACH ROW EXECUTE FUNCTION public.sisadmi_identification_kind_code_guard();
"""

REVERSE_SQL = r"""
DROP TRIGGER people_identification_kind_code_immutable ON public.people_identificationkind;
DROP FUNCTION public.sisadmi_identification_kind_code_guard();
DROP TRIGGER people_person_identity_coherent ON public.people_person;
DROP FUNCTION public.sisadmi_person_identity_insert_guard();
DROP TRIGGER people_person_identity_immutable ON public.people_person;
DROP FUNCTION public.sisadmi_person_identity_guard();
"""


class Migration(migrations.Migration):
    dependencies = [('people', '0010_identification_catalog_and_final_consumer')]
    operations = [migrations.RunSQL(FORWARD_SQL, reverse_sql=REVERSE_SQL)]
