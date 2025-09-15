from django.contrib import admin

from .models import Category, Question


class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort']


class QuestionAdmin(admin.ModelAdmin):
    list_display = ['question', 'sort']


admin.site.register(Question, QuestionAdmin)
admin.site.register(Category, CategoryAdmin)
