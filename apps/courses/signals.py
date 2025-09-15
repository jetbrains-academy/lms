from django.db.models.signals import post_save
from django.dispatch import receiver

from courses.models import Course, CourseProgramBinding


@receiver(post_save, sender=Course)
def update_binding_timezones(sender, instance: Course, created, *args, **kwargs):
    if created or not instance.tracker.has_changed('time_zone'):
        return
    old_tz = instance.tracker.previous('time_zone')

    for binding in CourseProgramBinding.objects.filter(course=instance).all():
        binding.enrollment_end_date = (
            binding.enrollment_end_date
            .astimezone(old_tz)
            .replace(tzinfo=instance.time_zone)
        )
        binding.save()
