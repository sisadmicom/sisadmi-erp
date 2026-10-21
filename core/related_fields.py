"""Explicit maintenance capabilities; neither ForeignKeys nor browser names authorize actions."""
from dataclasses import dataclass
from core.action_presentation import entity_action


@dataclass(frozen=True)
class RelatedAction:
    operation: str
    label: str
    endpoint: str
    permission: str
    submit_name: str = 'related'
    submit_value: str = ''


@dataclass(frozen=True)
class RelatedField:
    entity: str
    label: str
    actions: tuple
    selection_policy: str
    integrity_policy: str
    return_policy: str = 'actor-bound-parent-draft'

    def controls(self, actor, field, *, allowed=True):
        selected = field.value()
        try:
            selected = int(selected)
        except (TypeError, ValueError):
            selected = None
        selected = bool(selected and field.field.queryset.filter(pk=selected).exists())
        return [entity_action('edit' if action.operation == 'change' else action.operation,
                     action.label + ' ' + self.label, name=action.submit_name,
                     value=action.submit_value or action.operation + ':' + self.entity)
                for action in self.actions
                if allowed and actor.is_authenticated and actor.is_active
                and (not action.permission or actor.has_perm(action.permission))
                and (action.operation == 'add' or selected)]


def field_rows(form, definitions, actor, *, allowed=True):
    return [dict(field=field, actions=definitions[field.name].controls(actor, field, allowed=allowed)
                 if field.name in definitions else []) for field in form.visible_fields()]
