"""Short-lived server-owned form drafts; return destinations are route names."""

import secrets
import time

from django.urls import reverse

SESSION_KEY = "people_ui_drafts"
MAX_AGE = 1800
MAX_DRAFTS = 6


def _context(request):
    company = request.active_company
    return request.user.pk, company.pk if company else None


def _entries(request, *, prune=True):
    actor, company = _context(request)
    now = time.time()
    stored = request.session.get(SESSION_KEY, {})
    entries = {token: draft for token, draft in stored.items()
               if draft["actor"] == actor and draft["company"] == company
               and now - draft["created"] < MAX_AGE}
    if prune and entries != stored:
        request.session[SESSION_KEY] = entries
    return entries


def read(request, token, *, prune=True):
    # A caller rejecting a continuation can inspect expiry without rewriting
    # the session. Existing consumers retain their automatic pruning.
    return _entries(request, prune=prune).get(token) if token else None


def save(request, *, route, object_id, fields, data, parent=None, multiple=(), booleans=()):
    entries = _entries(request)
    while len(entries) >= MAX_DRAFTS:
        entries.pop(next(iter(entries)))
    token = secrets.token_urlsafe(24)
    actor, company = _context(request)
    entries[token] = {
        "actor": actor, "company": company, "created": time.time(),
        "route": route, "object_id": object_id,
        "data": ({key: (list(data.getlist(key)) if hasattr(data, 'getlist') else list(data.get(key, [])))
                       if key in multiple else bool(data.get(key)) if key in booleans
                       else str(data.get(key, '')) for key in fields if key in data}
                 if multiple or booleans else {key: str(data.get(key, "")) for key in fields}),
        "parent": parent,
    }
    request.session[SESSION_KEY] = entries
    return token


def destination(token, draft):
    args = [draft["object_id"]] if draft["object_id"] else []
    return reverse(draft["route"], args=args) + "?draft=" + token


def select(request, token, kind, instance):
    entries = _entries(request)
    draft = entries[token]
    data = draft["data"]
    data[kind] = str(instance.pk)
    # A changed parent must not keep incompatible descendants. Restore coherent
    # ancestors too when a related record was moved to another parent.
    from people.forms import GEOGRAPHIC_FIELDS
    position = GEOGRAPHIC_FIELDS.index(kind)
    child = instance
    for ancestor in reversed(GEOGRAPHIC_FIELDS[:position]):
        child = getattr(child, ancestor)
        if ancestor in data:
            data[ancestor] = str(child.pk)
    from people.forms import GEOGRAPHY, valid_id
    parent_id = instance.pk
    for descendant in GEOGRAPHIC_FIELDS[position + 1:]:
        selected = GEOGRAPHY[descendant][0].objects.filter(
            pk=valid_id(data.get(descendant)),
            **{GEOGRAPHIC_FIELDS[GEOGRAPHIC_FIELDS.index(descendant) - 1] + "_id": parent_id},
        ).first() if parent_id else None
        if selected is None:
            data.pop(descendant, None)
            parent_id = None
        else:
            parent_id = selected.pk
    request.session[SESSION_KEY] = entries


def clear(request):
    request.session.pop(SESSION_KEY, None)


def update(request, token, **changes):
    """Change a server-owned draft without introducing another draft store."""
    entries = _entries(request)
    if token not in entries:
        raise KeyError(token)
    entries[token].update(changes)
    request.session[SESSION_KEY] = entries
    return entries[token]


def discard(request, token):
    entries = _entries(request)
    entries.pop(token, None)
    request.session[SESSION_KEY] = entries


RELATED_PURPOSE = 'related-maintenance'


def begin_related(request, *, route, object_id, fields, data, parent, entity, operation, selected):
    token = save(request, route=route, object_id=object_id, fields=fields, data=data, parent=parent)
    update(request, token, purpose=RELATED_PURPOSE, state='waiting',
           parent_entity=route.rsplit('_', 1)[0],
           parent_operation='change' if object_id else 'add',
           related_field=entity, related_entity=entity,
           related_operation=operation, selected_object=selected)
    return token


def resolve_related(request, token, *, route, object_id, entity, operation):
    """A token has exactly one child operation, then one bound parent form."""
    from django.core.exceptions import PermissionDenied
    if not token:
        return {}, None, False
    draft = read(request, token)
    if not draft or draft.get('purpose') != RELATED_PURPOSE:
        raise PermissionDenied
    if draft.get('state') == 'ready':
        if draft['route'] != route or draft['object_id'] != object_id:
            raise PermissionDenied
        return dict(draft['data']), draft.get('parent'), True
    if (draft.get('state') != 'waiting' or draft.get('related_entity') != entity
            or draft.get('related_field') != entity
            or draft.get('related_operation') != operation
            or draft.get('selected_object') != object_id):
        raise PermissionDenied
    return {}, token, False


def complete_related(request, token, *, entity, instance=None, deleted=False):
    from django.core.exceptions import PermissionDenied
    draft = read(request, token)
    if (not draft or draft.get('purpose') != RELATED_PURPOSE or draft.get('state') != 'waiting'
            or draft.get('related_entity') != entity or draft.get('related_field') != entity):
        raise PermissionDenied
    if instance is not None:
        if draft['related_operation'] == 'change' and instance.pk != draft['selected_object']:
            raise PermissionDenied
        select(request, token, entity, instance)
    if deleted:
        from people.forms import GEOGRAPHIC_FIELDS
        data = dict(read(request, token)['data'])
        for field in GEOGRAPHIC_FIELDS[GEOGRAPHIC_FIELDS.index(entity):]:
            if field in data:
                data[field] = ''
        update(request, token, data=data)
    draft = update(request, token, state='ready')
    return destination(token, draft)


def find(request, **criteria):
    """Find an existing transition within the same actor, Company and session."""
    return next(((token, draft) for token, draft in _entries(request).items()
                 if all(draft.get(key) == value for key, value in criteria.items())), (None, None))
