"""Authorized Company-scoped supplier maintenance; no Branch requirement."""
from people.models import Supplier
from people.services.commercial_relationship_maintenance import CommercialRelationshipMaintenance

_service = CommercialRelationshipMaintenance(Supplier, ('notes',))


def create(*, actor, company, person_id, data):
    return _service.create(actor=actor, company=company, person_id=person_id, data=data)


def list_relations(*, actor, company, query=None, include_inactive=False):
    return _service.list_relations(actor=actor, company=company, query=query, include_inactive=include_inactive)


def get_relation(*, actor, company, relation_id):
    return _service.get_relation(actor=actor, company=company, relation_id=relation_id)


def update(*, actor, company, relation_id, data):
    return _service.update(actor=actor, company=company, relation_id=relation_id, data=data)


def set_active(*, actor, company, relation_id, is_active):
    return _service.set_active(actor=actor, company=company, relation_id=relation_id, is_active=is_active)
