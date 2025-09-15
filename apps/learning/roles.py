from django.utils.translation import gettext_lazy as _
from djchoices import C, DjangoChoices

from alumni.permissions import ViewAlumniMenu
from auth.permissions import Role
from auth.registry import role_registry
from courses.permissions import (
    CreateAssignment, CreateCourseClass, CreateOwnAssignment, CreateOwnCourseClass,
    DeleteAssignment, DeleteAssignmentAttachment, DeleteAssignmentAttachmentAsTeacher,
    DeleteCourseClass, DeleteOwnAssignment, DeleteOwnCourseClass, EditAssignment,
    EditCourse, EditCourseClass, EditMetaCourse, EditOwnAssignment, EditOwnCourse,
    EditOwnCourseClass, ViewAssignment, ViewCourse, ViewCourseAssignments,
    ViewCourseClassMaterials, ViewCourseContacts, ViewCourseContactsAsLearner,
    ViewCourseContactsAsTeacher, ViewCourseInternalDescription,
    ViewCourseInternalDescriptionAsLearner, ViewCourseInternalDescriptionAsTeacher,
    ViewOwnAssignment
)
from users.permissions import (
    CreateCertificateOfParticipation, ViewAccountConnectedServiceProvider,
    ViewCertificateOfParticipation, UpdateStudentProfileStudentId, ViewProfile, ViewOwnProfile, ViewLearnerProfile
)
from .permissions import (
    AccessTeacherSection, CreateAssignmentComment, CreateAssignmentCommentAsLearner,
    CreateAssignmentCommentAsTeacher, CreateAssignmentSolution, CreateCourseNews,
    CreateOwnAssignmentSolution, CreateOwnCourseNews, CreateStudentGroup,
    CreateStudentGroupAsTeacher, DeleteCourseNews, DeleteOwnCourseNews,
    DeleteStudentGroup, DeleteStudentGroupAsTeacher, DownloadAssignmentSolutions,
    EditCourseNews, EditGradebook, EditOwnAssignmentExecutionTime, EditOwnCourseNews,
    EditOwnGradebook, EditOwnStudentAssignment, EditStudentAssignment, EnrollInCourse,
    LeaveCourse, UpdateStudentGroup,
    UpdateStudentGroupAsTeacher, ViewAssignmentAttachment,
    ViewAssignmentAttachmentAsLearner, ViewAssignmentAttachmentAsTeacher,
    ViewAssignmentCommentAttachment, ViewAssignmentCommentAttachmentAsLearner,
    ViewAssignmentCommentAttachmentAsTeacher, ViewCourseEnrollment,
    ViewCourseEnrollments, ViewCourseNews, ViewCourseReviews, ViewCourses,
    ViewEnrollment, ViewEnrollments, ViewGradebook, ViewLibrary,
    ViewOwnEnrollment, ViewOwnEnrollments, ViewOwnGradebook, ViewOwnStudentAssignment,
    ViewOwnStudentAssignments, ViewRelatedStudentAssignment, ViewSchedule,
    ViewStudentAssignment, ViewStudentAssignmentList, ViewStudentGroup,
    ViewStudentGroupAsTeacher, ViewStudyMenu, ViewTeachingMenu
)


# TODO: Add description to each role
class Roles(DjangoChoices):
    CURATOR = C(5, _('Curator'), priority=0, permissions=(
        ViewProfile,
        AccessTeacherSection,
        ViewAccountConnectedServiceProvider,
        ViewCourse,
        ViewCourseInternalDescription,
        EditCourse,
        CreateCertificateOfParticipation,
        ViewCertificateOfParticipation,
        EditMetaCourse,
        CreateAssignment,
        EditAssignment,
        ViewAssignment,
        DeleteAssignment,
        ViewCourseContacts,
        ViewCourseAssignments,
        ViewStudentAssignment,
        ViewStudentAssignmentList,
        EditStudentAssignment,
        CreateCourseClass,
        EditCourseClass,
        DeleteCourseClass,
        ViewCourseNews,
        CreateCourseNews,
        EditCourseNews,
        DeleteCourseNews,
        ViewCourseReviews,
        ViewLibrary,
        ViewEnrollments,
        ViewEnrollment,
        CreateAssignmentCommentAsTeacher,
        ViewGradebook,
        EditGradebook,
        CreateAssignmentComment,
        CreateAssignmentSolution,
        DownloadAssignmentSolutions,
        ViewAssignmentAttachment,
        DeleteAssignmentAttachment,
        ViewAssignmentCommentAttachment,
        ViewStudentGroup,
        UpdateStudentGroup,
        DeleteStudentGroup,
        CreateStudentGroup,
        UpdateStudentProfileStudentId,
        ViewAlumniMenu,
    ))
    STUDENT = C(1, _('Student'), priority=50, permissions=(
        UpdateStudentProfileStudentId,
    ))
    INVITED = C(11, _('Invited User'), permissions=())
    TEACHER = C(2, _('Teacher'), priority=30, permissions=(
        ViewOwnProfile,
        ViewLearnerProfile,
        ViewTeachingMenu,
        AccessTeacherSection,
        ViewCourse,
        ViewCourseInternalDescriptionAsTeacher,
        EditOwnCourse,
        ViewCourseContactsAsTeacher,
        ViewCourseNews,
        CreateOwnCourseNews,
        EditOwnCourseNews,
        DeleteOwnCourseNews,
        CreateOwnAssignment,
        EditOwnAssignment,
        ViewOwnAssignment,
        DeleteOwnAssignment,
        ViewCourseAssignments,
        ViewRelatedStudentAssignment,
        ViewStudentAssignmentList,
        EditOwnStudentAssignment,
        CreateOwnCourseClass,
        EditOwnCourseClass,
        DeleteOwnCourseClass,
        ViewCourseEnrollments,
        ViewCourseEnrollment,
        ViewAssignmentAttachmentAsTeacher,
        CreateAssignmentCommentAsTeacher,
        ViewAssignmentCommentAttachmentAsTeacher,
        DeleteAssignmentAttachmentAsTeacher,
        ViewOwnGradebook,
        EditOwnGradebook,
        ViewStudentGroupAsTeacher,
        UpdateStudentGroupAsTeacher,
        DeleteStudentGroupAsTeacher,
        CreateStudentGroupAsTeacher,
    ))
    ALUMNI = C(12, _('Alumni'), permissions=(
        ViewAlumniMenu,
    ))


for code, name in Roles.choices:
    choice = Roles.get_choice(code)
    role = Role(id=code, code=code, description=name,
                priority=getattr(choice, 'priority', 100),
                permissions=choice.permissions)
    role_registry.register(role)

# Add relations
teacher_role = role_registry[Roles.TEACHER]
teacher_role.add_relation(ViewProfile, ViewOwnProfile)
teacher_role.add_relation(ViewProfile, ViewLearnerProfile)
teacher_role.add_relation(ViewCourseContacts,
                          ViewCourseContactsAsTeacher)
teacher_role.add_relation(ViewCourseInternalDescription,
                          ViewCourseInternalDescriptionAsTeacher)
teacher_role.add_relation(EditCourse,
                          EditOwnCourse)
teacher_role.add_relation(ViewAssignmentAttachment,
                          ViewAssignmentAttachmentAsTeacher)
teacher_role.add_relation(DeleteAssignmentAttachment,
                          DeleteAssignmentAttachmentAsTeacher)
teacher_role.add_relation(CreateAssignmentComment,
                          CreateAssignmentCommentAsTeacher)
teacher_role.add_relation(ViewAssignmentCommentAttachment,
                          ViewAssignmentCommentAttachmentAsTeacher)
teacher_role.add_relation(ViewStudentAssignment, ViewRelatedStudentAssignment)
teacher_role.add_relation(EditStudentAssignment, EditOwnStudentAssignment)
teacher_role.add_relation(CreateCourseClass, CreateOwnCourseClass)
teacher_role.add_relation(EditCourseClass, EditOwnCourseClass)
teacher_role.add_relation(DeleteCourseClass, DeleteOwnCourseClass)
teacher_role.add_relation(CreateCourseNews, CreateOwnCourseNews)
teacher_role.add_relation(EditCourseNews, EditOwnCourseNews)
teacher_role.add_relation(DeleteCourseNews, DeleteOwnCourseNews)
teacher_role.add_relation(CreateAssignment, CreateOwnAssignment)
teacher_role.add_relation(EditAssignment, EditOwnAssignment)
teacher_role.add_relation(ViewAssignment, ViewOwnAssignment)
teacher_role.add_relation(DeleteAssignment, DeleteOwnAssignment)
teacher_role.add_relation(ViewEnrollments, ViewCourseEnrollments)
teacher_role.add_relation(ViewGradebook, ViewOwnGradebook)
teacher_role.add_relation(EditGradebook, EditOwnGradebook)
teacher_role.add_relation(ViewStudentGroup, ViewStudentGroupAsTeacher)
teacher_role.add_relation(CreateStudentGroup, CreateStudentGroupAsTeacher)
teacher_role.add_relation(DeleteStudentGroup, DeleteStudentGroupAsTeacher)
teacher_role.add_relation(UpdateStudentGroup, UpdateStudentGroupAsTeacher)
teacher_role.add_relation(ViewEnrollment, ViewCourseEnrollment)

common_student_perms = (
    ViewOwnProfile,
    ViewCourse,
    ViewCourseInternalDescriptionAsLearner,
    ViewStudyMenu,
    ViewCourseContactsAsLearner,
    ViewCourseAssignments,
    ViewCourseNews,
    ViewCourseReviews,
    ViewOwnEnrollments,
    ViewOwnEnrollment,
    ViewOwnStudentAssignments,
    ViewOwnStudentAssignment,
    ViewAssignmentAttachmentAsLearner,
    CreateAssignmentCommentAsLearner,
    CreateOwnAssignmentSolution,
    ViewAssignmentCommentAttachmentAsLearner,
    EditOwnAssignmentExecutionTime,
    ViewCourses,
    ViewSchedule,
    ViewLibrary,
    EnrollInCourse,
    LeaveCourse,
)

for role in (Roles.STUDENT, Roles.INVITED, Roles.ALUMNI):
    student_role = role_registry[role]
    for perm in common_student_perms:
        student_role.add_permission(perm)
    student_role.add_relation(ViewProfile, ViewOwnProfile)
    student_role.add_relation(ViewAssignmentAttachment,
                              ViewAssignmentAttachmentAsLearner)
    student_role.add_relation(ViewCourseContacts,
                              ViewCourseContactsAsLearner)
    student_role.add_relation(ViewCourseInternalDescription,
                              ViewCourseInternalDescriptionAsLearner)
    student_role.add_relation(CreateAssignmentComment,
                              CreateAssignmentCommentAsLearner)
    student_role.add_relation(CreateAssignmentSolution,
                              CreateOwnAssignmentSolution)
    student_role.add_relation(ViewAssignmentCommentAttachment,
                              ViewAssignmentCommentAttachmentAsLearner)
    student_role.add_relation(ViewEnrollment,
                              ViewOwnEnrollment)

anonymous_role = role_registry.anonymous_role
anonymous_role.add_permission(ViewCourseClassMaterials)
