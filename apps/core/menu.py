import re
from importlib import import_module
from typing import Iterable, Optional, Sequence, Callable

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from menu import Menu as _Menu
from menu import MenuItem as _MenuItem

from core.http import HttpRequest


class Menu(_Menu):
    @classmethod
    def load_menus(cls):
        super().load_menus()
        module = getattr(settings, "LMS_MENU", None)
        if module:
            try:
                import_module(module)
            except ModuleNotFoundError:
                raise ImproperlyConfigured("settings.LMS_MENU module not found")

    @classmethod
    def process(cls, request, name=None):
        visible = super().process(request, name)

        for item in visible:
            if any(child.selected for child in item.children):
                item.selected = True
                break

        return visible

class MenuItem(_MenuItem):
    """
    Note:
        Only one item would be considered as selected.
        The last one in case of ambiguity.
    """
    for_staff = False
    visible: bool
    permissions: Optional[Sequence[str]] = None
    # Additional check that item should be selected
    selected_patterns: list[re.Pattern]
    match_func: Optional[Callable[[HttpRequest], bool]] = None

    def __init__(self, *args, selected_patterns: Optional[Iterable[str]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        if selected_patterns is None:
            selected_patterns = []
        self.selected_patterns = [re.compile(x) for x in selected_patterns]

    def check(self, request):
        """Update menu item visibility for this request"""
        if self.permissions is not None:
            self.visible = request.user.has_perms(self.permissions)
        if callable(self.check_func):
            self.visible = self.check_func(request)
        if self.for_staff and not request.user.is_curator:
            self.visible = False

    def match_url(self, request: HttpRequest):
        """match url determines if this is selected"""
        matched = False
        url = str(self.url)
        if url.startswith('http'):
            raise ValueError('Use relative urls for menu')
        if re.match(url, request.path):
            matched = True
        if not matched and any(pattern.match(request.path) for pattern in self.selected_patterns):
            matched = True
        if not matched and self.match_func and self.match_func(request):
            matched = True
        return matched
