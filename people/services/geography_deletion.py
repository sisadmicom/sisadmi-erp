"""Conservative integrity policy for the explicitly maintained geography catalogs."""


def has_dependencies(instance):
    # Check references regardless of their configured PROTECT/CASCADE behavior.
    return any(relation.related_model._base_manager.filter(
        **{relation.field.name: instance}).exists()
        for relation in instance._meta.related_objects)
