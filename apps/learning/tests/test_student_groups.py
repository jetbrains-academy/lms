import pytest
from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from django.utils.encoding import smart_bytes

from auth.mixins import PermissionRequiredMixin
from auth.permissions import perm_registry
from core.tests.factories import AcademicProgramRunFactory, AcademicProgramFactory
from core.urls import reverse
from courses.models import (
    CourseGroupModes, CourseTeacher, StudentGroupTypes
)
from courses.tests.factories import (
    AssignmentFactory, CourseFactory, CourseTeacherFactory, SemesterFactory, CourseProgramBindingFactory
)
from learning.models import Enrollment, StudentAssignment, StudentGroup
from learning.permissions import DeleteStudentGroup, ViewStudentGroup
from learning.services import EnrollmentService, StudentGroupService
from learning.settings import GradeTypes
from learning.teaching.forms import StudentGroupForm
from learning.teaching.utils import get_student_groups_url
from learning.tests.factories import (
    CourseInvitationBindingFactory, EnrollmentFactory, StudentGroupAssigneeFactory, StudentGroupFactory
)
from users.tests.factories import (
    CuratorFactory, InvitedStudentFactory, StudentFactory, StudentProfileFactory,
    TeacherFactory
)


@pytest.mark.django_db
def test_model_student_group_mutually_exclusive_fields(settings):
    course = CourseFactory()
    student_group = StudentGroup(type=StudentGroupTypes.PROGRAM,
                                 name='test',
                                 course=course)
    with pytest.raises(ValidationError) as e:
        student_group.full_clean()
    student_group.program = AcademicProgramFactory()
    student_group.full_clean()
    student_group.program_run = AcademicProgramRunFactory()
    with pytest.raises(ValidationError) as e:
        student_group.full_clean()
    student_group.type = StudentGroupTypes.PROGRAM_RUN
    student_group.program = None
    student_group.full_clean()


@pytest.mark.django_db
def test_create_default_student_group(settings):
    course = CourseFactory(group_mode=CourseGroupModes.MANUAL)
    student_groups = StudentGroup.objects.filter(course=course).all()
    assert len(student_groups) == 1
    sg = student_groups[0]
    assert sg.program_id is None
    assert sg.program_run_id is None
    assert sg.type == StudentGroupTypes.SYSTEM
    assert sg.name == 'Others'


@pytest.mark.django_db
def test_upsert_student_group_from_additional_program(program_cub001, program_nup001):
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    binding_cub = CourseProgramBindingFactory(course=course, program=program_cub001)
    EnrollmentFactory(
        course=course,
        course_program_binding=binding_cub,
        student_profile__academic_program_enrollment__program=program_cub001,
    )
    assert StudentGroup.objects.filter(course=course).count() == 1
    binding_nup = CourseProgramBindingFactory(course=course, program=program_nup001)
    nup_enrollment = EnrollmentFactory(
        course=course,
        course_program_binding=binding_nup,
        student_profile__academic_program_enrollment__program=program_nup001,
    )
    groups = StudentGroup.objects.filter(course=course).order_by('pk')
    assert len(groups) == 2
    sg1, sg2 = groups
    assert sg1.type == StudentGroupTypes.PROGRAM
    assert sg2.type == StudentGroupTypes.PROGRAM
    assert sg1.program_id == program_cub001.pk
    assert sg2.program_id == program_nup001.pk

    nup_enrollment.delete()
    binding_nup.delete()
    groups = list(StudentGroup.objects.filter(course=course))
    assert len(groups) == 1
    group_programs = {sg.program for sg in groups}
    assert group_programs == {program_cub001}

    program_other = AcademicProgramFactory()
    binding_other = CourseProgramBindingFactory(course=course, program=program_other)
    groups = StudentGroup.objects.filter(course=course)
    assert len(groups) == 2
    group_programs = {sg.program for sg in groups}
    assert group_programs == {program_cub001, program_other}


@pytest.mark.django_db
def test_student_group_resolving_on_enrollment(client, program_cub001, program_run_cub):
    """
    Prevent enrollment if it's impossible to resolve student group by
    student's root branch.
    """
    student_profile1 = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    student_profile2 = StudentProfileFactory(academic_program_enrollment=AcademicProgramRunFactory())
    semester = SemesterFactory.create_current()
    course = CourseFactory(semester=semester)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    student_groups = StudentGroup.objects.filter(course=course).all()
    assert len(student_groups) == 1
    student_group = student_groups[0]
    enroll_url = course.get_enroll_url()
    form = {'course_pk': course.pk}
    client.login(student_profile1.user)
    response = client.post(enroll_url, form)
    assert response.status_code == 302
    enrollments = Enrollment.active.filter(student_profile=student_profile1,
                                           course=course).all()
    assert len(enrollments) == 1
    enrollment = enrollments[0]
    assert enrollment.student_group == student_group
    # No permission through public interface
    client.login(student_profile2.user)
    response = client.post(enroll_url, form)
    assert response.status_code == 403


@pytest.mark.django_db
def test_student_group_resolving_on_enrollment_admin(client, settings, program_cub001, program_run_cub):
    """
    Admin interface doesn't check all the requirements to enroll student.
    If it's impossible to resolve student group - add student to the
    special group `Others`.
    """
    student, student2 = StudentFactory.create_batch(
        2,
        student_profile__academic_program_enrollment=program_run_cub
    )
    course = CourseFactory()
    cpb = CourseProgramBindingFactory(course=course, program=program_cub001)
    post_data = {
        'course': course.pk,
        'course_program_binding': cpb.pk,
        'student': student.pk,
        'student_profile': student.get_student_profile().pk,
        'grade': GradeTypes.NOT_GRADED,
        'grade_history-TOTAL_FORMS': 0,
        'grade_history-INITIAL_FORMS': 0
    }
    curator = CuratorFactory()
    client.login(curator)
    response = client.post(reverse('admin:learning_enrollment_add'), post_data)
    enrollments = Enrollment.active.filter(student=student, course=course)
    assert len(enrollments) == 1
    e = enrollments[0]
    assert e.student_group_id is not None
    assert e.student_group.name == 'Others'
    assert e.student_group.type == StudentGroupTypes.SYSTEM
    # Enroll the second student
    post_data['student'] = student2.pk
    post_data['student_profile'] = student2.get_student_profile().pk
    response = client.post(reverse('admin:learning_enrollment_add'), post_data)
    e2 = Enrollment.active.filter(student=student2, course=course)
    assert e2.exists()
    assert e2.get().student_group == e.student_group


@pytest.mark.django_db
def test_student_group_resolving_enrollment_by_invitation(client):
    invited = InvitedStudentFactory()
    course = CourseFactory()
    student_groups = StudentGroup.objects.filter(course=course).all()
    assert len(student_groups) == 1
    student_group = student_groups[0]

    course_invitation = CourseInvitationBindingFactory(course=course)
    invitation = course_invitation.invitation

    client.login(invited)
    invitation_url = invitation.get_absolute_url()
    response = client.post(invitation_url)
    assert response.status_code == 302

    enrollment_url = course.get_enroll_url()
    response = client.post(enrollment_url, {})
    assert response.status_code == 302

    enrollments = Enrollment.active.filter(student=invited, course=course).all()
    assert len(enrollments) == 1
    enrollment = enrollments[0]
    assert enrollment.student_group == student_group
    assert enrollment.course_program_binding == course_invitation


@pytest.mark.django_db
def test_assignment_restricted_to(program_cub001, program_run_cub, program_nup001, program_run_nup):
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    binding_cub = CourseProgramBindingFactory(course=course, program=program_cub001)
    binding_nup = CourseProgramBindingFactory(course=course, program=program_nup001)
    groups = StudentGroup.objects.filter(course=course).order_by('pk')
    assert groups.count() == 2
    sg_cub, sg_nup = groups
    e_cub = EnrollmentFactory(
        course=course,
        course_program_binding=binding_cub,
        student_profile__academic_program_enrollment__program=program_cub001,
    )
    e_nup = EnrollmentFactory(
        course=course,
        course_program_binding=binding_nup,
        student_profile__academic_program_enrollment__program=program_nup001,
    )
    a = AssignmentFactory(course=course, restricted_to=[sg_cub])
    student_assignments = StudentAssignment.objects.filter(assignment=a)
    assert len(student_assignments) == 1
    assert student_assignments[0].student == e_cub.student


@pytest.mark.django_db
def test_view_student_group_list_permissions(client, lms_resolver):
    teacher = TeacherFactory()
    student = StudentFactory()
    course = CourseFactory(teachers=[teacher])
    url = get_student_groups_url(course)
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewStudentGroup.name
    assert resolver.func.view_class.permission_required in perm_registry
    client.login(teacher)
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_view_student_group_list_smoke(client, lms_resolver):
    teacher = TeacherFactory()
    course = CourseFactory.create(teachers=[teacher],
                                  group_mode=CourseGroupModes.MANUAL)
    student_group1 = StudentGroupFactory(course=course)
    student_group2 = StudentGroupFactory(course=course)

    client.login(teacher)
    url = get_student_groups_url(course)
    response = client.get(url)
    assert smart_bytes(student_group1.name) in response.content
    assert smart_bytes(student_group2.name) in response.content


@pytest.mark.django_db
def test_view_student_group_detail_permissions(client, lms_resolver):
    teacher = TeacherFactory()
    student = StudentFactory()
    course = CourseFactory(teachers=[teacher])
    student_group = StudentGroupFactory(course=course)
    student_group_other = StudentGroupFactory()
    url = student_group.get_absolute_url()
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewStudentGroup.name
    assert resolver.func.view_class.permission_required in perm_registry
    client.login(teacher)
    response = client.get(url)
    assert response.status_code == 200
    # Student group PK is not associated with the course from friendly URL
    url = reverse("teaching:student_groups:detail", kwargs={
        "pk": student_group_other.pk,
        **course.url_kwargs
    })
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_view_student_group_detail_smoke(client):
    teacher = TeacherFactory()
    student1, student2 = StudentFactory.create_batch(2)
    course = CourseFactory(teachers=[teacher], group_mode=CourseGroupModes.MANUAL)
    student_group1 = StudentGroupFactory(course=course)
    EnrollmentFactory(student=student1, course=course, student_group=student_group1)
    course_teacher = CourseTeacher.objects.filter(course=course).first()
    StudentGroupAssigneeFactory(assignee=course_teacher, student_group=student_group1)
    client.login(teacher)
    url = student_group1.get_absolute_url()
    response = client.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    assert student_group1.name in soup.find('h2').text
    assert smart_bytes(student1.last_name) in response.content
    assert smart_bytes(student2.last_name) not in response.content
    assert smart_bytes(teacher.last_name) in response.content


@pytest.mark.django_db
def test_view_student_group_delete(settings):
    teacher = TeacherFactory()
    course = CourseFactory(teachers=[teacher], group_mode=CourseGroupModes.MANUAL)
    student_group = StudentGroupFactory(course=course)
    assert teacher.has_perm(DeleteStudentGroup.name, student_group)
    enrollment = EnrollmentFactory(course=course, student_group=student_group)
    EnrollmentService.leave(enrollment)
    assert Enrollment.active.filter(course=course).count() == 0
    assert Enrollment.objects.filter(course=course).count() == 1
    # Student must be moved to the default student group if student's group
    # was deleted after student left the course
    StudentGroupService.remove(student_group)
    enrollment.refresh_from_db()
    assert enrollment.student_group == StudentGroupService.get_or_create_default_group(course)
    # Re-enter the course
    student_group = StudentGroupService.resolve(course, student_profile=enrollment.student_profile)
    EnrollmentService.enroll(enrollment.student_profile, course, student_group=student_group)
    enrollment.refresh_from_db()
    assert Enrollment.active.filter(course=course).count() == 1
    default_sg = StudentGroup.objects.get(course=course, type=StudentGroupTypes.SYSTEM)
    assert enrollment.student_group == default_sg


@pytest.mark.django_db
def test_form_student_group_assignee_update_doesnt_propose_spectators(settings):
    teacher_1, teacher_2, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(group_mode=CourseGroupModes.MANUAL)
    ct_1 = CourseTeacherFactory(course=course, teacher=teacher_1,
                                roles=CourseTeacher.roles.lecturer)
    ct_2 = CourseTeacherFactory(course=course, teacher=teacher_2,
                                roles=CourseTeacher.roles.organizer)
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    sg_form = StudentGroupForm(course)
    possible_assignees = sg_form.fields['assignee'].queryset
    assert len(possible_assignees) == 2
    assert {ct_1, ct_2} == set(possible_assignees)
