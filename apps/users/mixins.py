from django.contrib.auth.mixins import UserPassesTestMixin

# FIXME: remove


class TeacherOnlyMixin(UserPassesTestMixin):
    raise_exception = False

    def test_func(self):
        user = self.request.user
        return user.is_teacher or user.is_curator


class StudentOnlyMixin(UserPassesTestMixin):
    raise_exception = False

    def test_func(self):
        user = self.request.user
        return user.is_active_student or user.is_curator


class CuratorOnlyMixin(UserPassesTestMixin):
    raise_exception = False

    def test_func(self):
        return self.request.user.is_curator
