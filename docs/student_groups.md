## Student Groups

The concept of a student group is very simple - it's a subset of all students in a particular course.
A group has a name and supervisors.

Each student must belong to a group, but only one - group intersections by students are not allowed.
At the moment of course enrollment, a decision is made about which group to place the student in.
There are two operating modes for course student groups to make this decision. The operating mode can be specified in the course settings only at the moment of its creation; after course creation - only by request.

### "Department" Student Group Mode

The mode is fully automated and handles the distribution of course students by departments available within the course.

When adding a new department for which the course is available, a student group linked to this department is created (the group name matches the department name).

Then, at the moment of course enrollment, we look at the student's home department (the one specified in their current student profile) and link the student with the corresponding department-group.

Enrolling a student in a course when their home department is not among those available within the course can only be done through the admin panel. In this case, a student group "Others" is automatically created, and all students for whom no department-group is found will be placed in this system group.

### "Manual" Student Group Mode

There's no hidden logic here, except that we need a default group where students will be placed when enrolling in the course.
It, like in the case of "Department" mode, is created automatically when students enroll in the course.

Through the public interface, instructors can create the groups they need and move students from groups to target ones.

## Student Group Supervisors

A student group supervisor is an instructor who will most likely be assigned as a reviewer if a student shows activity in any assignment (sends a comment or solution to an assignment), but only on the condition that no reviewer has been assigned yet at that point (one of the instructors could have already designated themselves as a reviewer for some reason).

The public interface currently allows assigning only one supervisor.

When an instructor is specified as a reviewer for a personal assignment (personal means one that contains a student's progress on a specific assignment), only they receive notifications about student activity. It turns out that the reviewer is the instructor who won the race among supervisors.

Note: Through the admin panel there's a technical possibility to set multiple supervisors, but it should be noted that the list will be reset if the student group is edited through the public interface after adding multiple supervisors.
If multiple supervisors are specified, then a reviewer is not automatically assigned, since it's not entirely clear which one of them should be it (the logic of "supervisor among supervisors" who would transfer students to other supervisors reduces to specifying one supervisor, i.e., unnecessary complication).
As a consequence, all student group supervisors will receive notifications (instead of all homework reviewers specified in course settings), until one of them takes the student for themselves by designating themselves as a reviewer on the assignment review page.

## Moving Students Between Student Groups

In the student group editing form, there's a possibility to move some students to another group, but with one limitation - when moving a student, we can only add new personal assignments.

You can follow the rule - if an assignment was available to the student in the source group, then it must be available in the new (target) group.

The motivation for the limitation - deleting a personal assignment when transferring a student can be a non-obvious action. Additionally, the student might have already started working on the assignment. It would be a surprise for them when they log into the site to submit a solution, and it's no longer there for a reason unknown to them.
