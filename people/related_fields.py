"""The maintained relations are declared here, independent of model introspection."""
from core.related_fields import RelatedAction, RelatedField


def geography_relation(entity, label):
    return RelatedField(entity, label, tuple(
        RelatedAction(operation, text, entity + suffix, 'people.' + operation + '_' + entity)
        for operation, text, suffix in (('add', 'Adicionar', '_create'),
                                       ('change', 'Editar', '_update'), ('delete', 'Eliminar', '_delete'))),
        'authorized-catalog-queryset', 'block-all-dependencies')


RELATIONS = {
    'continent': geography_relation('continent', 'continente'),
    'country': geography_relation('country', 'país'),
    'province': geography_relation('province', 'provincia'),
    'canton': geography_relation('canton', 'cantón'),
    'parish': geography_relation('parish', 'parroquia'),
}
PARENTS = {'country': ('continent',), 'province': ('country',),
           'canton': ('province',), 'parish': ('canton',), 'continent': (),
           'person': ('continent', 'country', 'province', 'canton', 'parish'),
           # Existing auxiliary location filter and legacy setup retain their controls.
           'initial_setup': tuple(RELATIONS)}


def definitions(parent):
    return {field: RELATIONS[field] for field in PARENTS[parent]}
