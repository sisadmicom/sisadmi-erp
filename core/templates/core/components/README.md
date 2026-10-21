# Lenguaje de acciones SISADMI

Decisión humana D-02A.1: Adicionar (+), Consultar (lupa), Editar (lápiz) y
Eliminar (−). Los cuatro SVG son locales: `core/static/core/icons/`.

`core.action_presentation.entity_action` recibe una capacidad ya autorizada
por el servidor y produce los datos para `entity_action.html`. El componente
representa un enlace normal o un submit normal; no determina permisos, scope
ni endpoints. Los nombres accesibles deben identificar la entidad, por
ejemplo «Eliminar país». El texto «Borrar» queda sustituido en la interfaz.

Las relaciones declaradas en `RelatedField` conservan sus operaciones y
continuaciones. Los iconos no conceden capacidades nuevas. Una ForeignKey
no implica autorización para crear, consultar, editar ni eliminar.

Eliminar inicia confirmación mediante GET; la escritura requiere POST,
CSRF, autorización revalidada e integridad. Geography conserva el bloqueo
conservador de dependencias, incluso cuando Django permitiría CASCADE.

## Hallazgo pendiente: eliminación de Person

El listado todavía no ofrece Eliminar persona. D-02B.1a define visibilidad,
creación y administración, pero no una política de eliminación. Toda Person
visible está vinculada mediante CompanyPersonAccess. Antes de habilitar la
operación debe definirse su contrato de eliminación y el tratamiento de
esas asociaciones, conservando scope y evitando cascadas accidentales.

La aplicación actual abarca Person, Geography y Company → Person.
Los futuros mantenimientos deben reutilizar este componente y declarar sus
capacidades explícitamente. La validación visual humana sigue pendiente.
