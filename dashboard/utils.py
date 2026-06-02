from django.contrib.sessions.backends.base import SessionBase
from django.forms import BaseForm
from django.forms.utils import ErrorDict, ErrorList

from savings.models import Parameter

def get_parameter(key: str, default=None):
    try:
        return Parameter.objects.get(key=key).value
    except Parameter.DoesNotExist:
        return default