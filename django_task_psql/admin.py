from django.contrib import admin

from .models import TaskRow


@admin.register(TaskRow)
class TaskRowAdmin(admin.ModelAdmin):
    list_display = ("id", "task_path", "queue_name", "status", "attempt", "max_attempts", "enqueued_at", "finished_at")
    list_filter = ("status", "queue_name", "backend_name")
    search_fields = ("task_path", "id")
    readonly_fields = [f.name for f in TaskRow._meta.fields]
    ordering = ("-enqueued_at",)

    def has_add_permission(self, request):
        return False
