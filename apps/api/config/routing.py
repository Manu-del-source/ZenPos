from rest_framework.routers import DefaultRouter


class ModuleRouter(DefaultRouter):
    """Router for a single domain module.

    The API root view and format suffixes are disabled. Several module routers
    are mounted under the same ``/api/v2/`` prefix, and each one would otherwise
    register its own ``api-root`` URL name, producing duplicate-name warnings on
    startup and unpredictable ``reverse()`` results.
    """

    include_root_view = False
    include_format_suffixes = False
