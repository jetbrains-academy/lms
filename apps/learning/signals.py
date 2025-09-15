from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_rq import get_queue

from courses.constants import AssignmentFormat
from courses.models import (
    Assignment, Course, CourseGroupModes, CourseNews, CourseTeacher,
    StudentGroupTypes, CourseProgramBinding
)
from learning.models import (
    AssignmentComment, AssignmentNotification, AssignmentSubmissionTypes,
    CourseNewsNotification, Enrollment, StudentAssignment, StudentGroup
)
from learning.services import StudentGroupService
from learning.services.enrollment_service import update_course_learners_count
from learning.services.jba_service import JbaService
# FIXME: post_delete нужен? Что лучше - удалять StudentGroup + SET_NULL у Enrollment или делать soft-delete?
# FIXME: группу лучше удалить, т.к. она будет предлагаться для новых заданий, хотя типа уже удалена.
from learning.tasks import convert_assignment_submission_ipynb_file_to_html
from notifications.tasks import send_assignment_notifications, send_course_news_notifications


@receiver(post_save, sender=Course)
def create_student_group_from_course(sender, instance: Course,
                                     created, *args, **kwargs):
    if created and instance.group_mode == CourseGroupModes.MANUAL:
        StudentGroupService.get_or_create_default_group(instance)


@receiver(post_save, sender=CourseProgramBinding)
def create_student_group_from_program_binding(sender, instance: CourseProgramBinding, created, *args, **kwargs):
    if created and instance.course.group_mode == CourseGroupModes.PROGRAM:
        StudentGroupService.create(
            instance.course,
            group_type=StudentGroupTypes.PROGRAM,
            program=instance.program
        )


@receiver(post_delete, sender=CourseProgramBinding)
def delete_student_group_if_program_binding_deleted(sender, instance: CourseProgramBinding, *args, **kwargs):
    if instance.course.group_mode != CourseGroupModes.PROGRAM:
        return

    student_group = (
        StudentGroup.objects
        .filter(
            course=instance.course,
            program=instance.program,
            type=StudentGroupTypes.PROGRAM
        )
        .first()
    )
    StudentGroupService.remove(student_group)


def delete_program_run_student_group_if_needed(instance: Enrollment):
    if instance.course.group_mode != CourseGroupModes.PROGRAM_RUN:
        return

    program_run = instance.student_profile.academic_program_enrollment
    any_enrollment_for_program_run_left = (
        Enrollment.objects
        .exclude(pk=instance.pk)
        .filter(
            course=instance.course,
            student_profile__academic_program_enrollment=program_run
        )
        .exists()
    )
    if any_enrollment_for_program_run_left:
        return

    student_group = (
        StudentGroup.objects
        .filter(
            course=instance.course,
            program_run=program_run,
            type=StudentGroupTypes.PROGRAM_RUN
        )
        .first()
    )
    StudentGroupService.remove(student_group)


@receiver(post_delete, sender=Enrollment)
def delete_program_run_student_group_if_needed_on_delete(sender, instance: Enrollment, *args, **kwargs):
    delete_program_run_student_group_if_needed(instance)


@receiver(post_save, sender=Enrollment)
def delete_program_run_student_group_if_needed_on_save(sender, instance: Enrollment, created, *args, **kwargs):
    # enrollments are created with is_deleted=True
    if not created and instance.is_deleted:
        delete_program_run_student_group_if_needed(instance)


@receiver(post_save, sender=Enrollment)
def compute_course_learners_count(sender, instance: Enrollment, created,
                                  *args, **kwargs):
    # enrollments are created with is_deleted=True
    if created and instance.is_deleted:
        return
    update_course_learners_count(instance.course_id)


@receiver(post_save, sender=CourseNews)
def create_notifications_about_course_news(sender, instance: CourseNews,
                                           created, *args, **kwargs):
    if not created:
        return
    co_id = instance.course_id
    notifications = []
    active_enrollments = Enrollment.active.filter(course_id=co_id)
    for e in active_enrollments.iterator():
        notifications.append(
            CourseNewsNotification(user_id=e.student_id,
                                   course_offering_news_id=instance.pk))
    teachers = CourseTeacher.objects.filter(course_id=co_id)
    for co_t in teachers.iterator():
        notifications.append(
            CourseNewsNotification(user_id=co_t.teacher_id,
                                   course_offering_news_id=instance.pk))
    CourseNewsNotification.objects.bulk_create(notifications)
    send_course_news_notifications.delay([x.id for x in notifications])


@receiver(post_save, sender=Assignment)
def create_deadline_change_notification(sender, instance: Assignment, created,
                                        *args, **kwargs):
    if (
        created
        or 'deadline_at' not in instance.tracker.changed()
        or not instance.open_date_passed
    ):
        return
    active_enrollments = Enrollment.active.filter(course=instance.course)
    notification_ids = []
    for e in active_enrollments:
        try:
            sa = (StudentAssignment.objects
                  .only('pk')
                  .get(student_id=e.student_id,
                       assignment=instance))
        except StudentAssignment.DoesNotExist:
            # It can occur for student with inactive status
            continue
        obj = AssignmentNotification(
            user_id=e.student_id,
            student_assignment_id=sa.pk,
            is_about_deadline=True
        )
        obj.save()
        notification_ids.append(obj.id)
    send_assignment_notifications.delay(notification_ids)


@receiver(post_save, sender=Assignment)
def schedule_jba_progress_update_at_deadline(
    sender, instance: Assignment, created,
    *args, **kwargs
):
    if (
        (not created and 'deadline_at' not in instance.tracker.changed())
        or instance.submission_type != AssignmentFormat.JBA
    ):
        return
    queue = get_queue('default')
    queue.enqueue_at(
        instance.deadline_at,
        JbaService.update_assignment_progress,
        job_id=f'update_jba_progress_at_deadline_{instance.pk}',
        assignment=instance.pk,
        at_deadline=True,
    )


@receiver(post_save, sender=AssignmentComment)
def convert_ipynb_files(sender, instance: AssignmentComment, *args, **kwargs):
    # TODO: convert for solutions only? both?
    if not instance.attached_file:
        return
    if instance.attached_file_name.endswith('.ipynb'):
        kwargs = {'assignment_submission_id': instance.pk}
        # FIXME: add transaction.on_commit
        convert_assignment_submission_ipynb_file_to_html.delay(**kwargs)


# TODO: move to the create_assignment_solution service method
@receiver(post_save, sender=AssignmentComment)
def save_student_solution(sender, instance: AssignmentComment, *args, **kwargs):
    """Updates aggregated execution time value on StudentAssignment model"""
    if instance.type != AssignmentSubmissionTypes.SOLUTION:
        return
    instance.student_assignment.compute_fields('execution_time')


@receiver(post_delete, sender=AssignmentComment)
def delete_student_solution(sender, instance: AssignmentComment,
                            *args, **kwargs):
    """Updates aggregated execution time value on StudentAssignment model"""
    if instance.type != AssignmentSubmissionTypes.SOLUTION:
        return
    instance.student_assignment.compute_fields('execution_time')
