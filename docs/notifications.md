### Implementation Details

Only email notifications are supported. They are currently stored in different models without a common interface:

1. learning.AssignmentNotification:
    is_about_passed - new solution
    is_about_creation - assignment created (for student)
    is_about_deadline - deadline changed

2. learning.CourseNewsNotification:
    course news created

3. post_office.Email:
    Third-party application for mailing. Actively used for Enrollment.

4. notification.Notification:
    Notifications in Atom Syndication Format, currently used only for project notifications
    Not sure if we need this format (is a data format used for providing users with frequently updated content - like RSS replacement). It implies a feed where someone does something, but in fact we usually don't have an actor

There are 3 commands that send emails on schedule:

* send_notification - sends all emails from notification.Notification. Currently contains only CS center project notifications.
* send_queued_mail - for sending emails from post_office application, all emails use `django_ses.SESBackend` as backend
* notify - sending notifications related to AssignmentNotification and CourseNewsNotification models.
Since notifications are not tied to a specific site, we can't rely on application settings when sending, so we need to store smtp settings in the DB and take them dynamically depending on the site the student is associated with.
(For example, from the SHAD site there might be an attempt to send an email to a CS center student who is enrolled in a SHAD course, i.e., it needs to be sent from the center's mailbox and links should lead to the center's site, since they likely registered through the CS Center site.
If we use SMTP settings from the SHAD application, the email will be sent from yandexdataschool.ru and all links will be to that domain).
SMTP connection settings for sites are stored in the SiteConfiguration model

P.S. projects_notification - poor naming, only generates reminders about the start/end of report submission period, emails are stored in notification.Notification model

Issues:
* email confirmation can hurt service rating. Keep on SMTP?


# Notifications

Notifications are sent only via email, sent by cron with a 5-minute delay.
Message body is generated at the time of sending. For some messages, Atom Syndication Format is used (like on github).
Physically, notifications are stored in different DB tables, each with its own format.
Unread notifications are deleted manually, storage period usually doesn't exceed a semester, or more precisely, until the first complaint "can't reset notification counter".
Read notifications are deleted by cron once a week.

Almost all notifications are mandatory, users cannot configure the events they need themselves.

A curator can only influence teacher notifications about new comments on assignments.

The workflow is as follows:

Each **assignment** has notification settings where a list of users who will receive notifications about new comments is specified.
In the **course enrollment** settings, when adding a teacher, you can set a checkbox "Automatically subscribe to notifications".
Then at the moment of assignment creation (and only then) all teachers with this checkbox set will be copied to the notification settings of the new assignment.
If a teacher was added after assignment creation and wants to receive notifications, they need to be added to notification settings manually.

Non-obvious point: If a teacher is not subscribed to assignment notifications, they won't see it on the assignments' page.

## Notification Types

#### Course News

Sent to all students subscribed to the course, as well as all course teachers.

#### New Assignment

Only students subscribed to the course will receive the notification.

#### Assignment Deadline Change

Only students subscribed to the course will receive the notification.

#### New Comment on Assignment

If the comment is from a teacher, expectedly only the student will receive the notification.

If the comment was left by a student, see the sending logic in code.

#### Start of Project Submission Reporting Period

Three days before the reporting period starts, students whose project hasn't been cancelled and who haven't received a negative score will receive a notification.
A repeated reminder that the registration deadline is approaching will be sent 1 day before the end.

#### New Project Report Submitted

All users with the `Project Curator` group will receive the notification.

#### New Comment on Project Report

Three groups receive notifications: report author (the student), project curators, and reviewers subscribed to the project related to the report.

Project curators and the student always receive notifications about new comments.

Reviewers receive notifications about new comments only if the current report status is "Review".

#### Survey Added to Course

Notification is generated when the survey is published (appropriate status must be set), recipients are only students subscribed to the course.

## Sending Notifications About Student Activity in Assignment

Whether a teacher receives a notification or not depends on three factors:
* Teacher's notification settings (curator can disable all notifications in course settings)
* If a personal assignment has a designated reviewer, only they will receive all notifications
* When creating an assignment, the selected responsible mode will determine how the list of responsible teachers who become notification recipients is formed

A reviewer can be assigned in two ways:
* manually at any time
* automatically at the moment of first student activity (new comment or new solution), if the length of the formed list of responsible teachers equals "1"

TODO: we can support a watcher list for anyone wanting to track assignment verification activity. For example, a curator subscribes to updates on a problematic student.

### Description of Responsible Modes

The responsible mode type is specified in assignment settings and is only considered if no reviewer is assigned.

# TODO: describe modes

### Send test email
