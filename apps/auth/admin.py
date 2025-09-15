from django.contrib import admin
from django.contrib.admin import AdminSite

from auth.forms import LoginForm

admin_site: AdminSite = admin.site
admin_site.login_form = LoginForm
admin_site.login_template = 'login.html'

