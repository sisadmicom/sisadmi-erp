"""Only the four approved Product annexes declare contextual capabilities."""
from dataclasses import dataclass

from core.related_fields import RelatedAction, RelatedField
from .models import Brand, ProductGroup, ProductSubGroup, UnitMeasure


@dataclass(frozen=True)
class ProductRelation:
    entity: str
    model: type
    route: str
    label: str

    def permission(self, operation):
        return f'catalog.{operation}_{self.entity}'

    def endpoint(self, operation):
        return self.route + {'add': '_create', 'view': '_detail', 'change': '_update'}[operation]

    def presentation(self, field):
        return RelatedField(self.entity, self.label, tuple(
            RelatedAction(op, label, self.endpoint(op), self.permission(op),
                          submit_value=op + ':' + field)
            for op, label in (('add', 'Adicionar'), ('view', 'Consultar'), ('change', 'Editar'))
        ), 'product-authorized-queryset', 'normal-annex-maintenance')


RELATIONS = {
    'unit_measure': ProductRelation('unitmeasure', UnitMeasure, 'unit', 'unidad'),
    'brand': ProductRelation('brand', Brand, 'brand', 'marca'),
    'group': ProductRelation('productgroup', ProductGroup, 'group', 'grupo'),
    'subgroup': ProductRelation('productsubgroup', ProductSubGroup, 'subgroup', 'subgrupo'),
}
