"""
Clock Shop project initialization.
"""

import sys

# Python 3.14+ compatibility patch for Django 4.2:
# In Python 3.14+, super() objects do not have a __dict__ and disallow setting
# new attributes, which breaks Django's BaseContext.__copy__ when rendering templates.
if sys.version_info >= (3, 14):
    from copy import copy
    import django.template.context

    def _base_context_copy(self):
        duplicate = django.template.context.BaseContext()
        duplicate.__class__ = self.__class__
        duplicate.__dict__ = copy(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    django.template.context.BaseContext.__copy__ = _base_context_copy
