from threading import local

from core.models import Company, Branch

def erp_context(request):

    return {
        "current_company": getattr(request, "company", None),
        "current_branch": getattr(request, "branch", None),
    }

_storage = local()


class CurrentContext:

    @classmethod
    def set(cls,key,value):

        setattr(_storage,key,value)

    @classmethod
    def get(cls,key):

        return getattr(_storage,key,None)

    @classmethod
    def clear(cls):

        _storage.__dict__.clear()