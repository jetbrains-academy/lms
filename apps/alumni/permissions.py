from auth.permissions import add_perm, Permission


@add_perm
class ViewAlumniMenu(Permission):
    name = 'alumni.view_alumni_menu'

