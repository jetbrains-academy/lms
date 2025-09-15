### Authorization Token

All API requests must contain the header `Authorization: Token <auth_token>`,
where `<auth_token>` is the authorization token, which can be obtained with the following request:

```python
import requests
LMS_DOMAIN = 'http://my.csc.test'
GET_TOKEN_ENDPOINT = f'{LMS_DOMAIN}/api/v1/token/'
response = requests.post(GET_TOKEN_ENDPOINT, data={'login':'email@example.com', 'password': '123123'})
auth_token = response.json()['secret_token']
```

The response contains the authorization token if the account credentials were provided correctly. The token is currently permanent, but in the future its lifetime may be limited to the current semester.

### Course List

```python
import requests

LMS_DOMAIN = 'http://my.csc.test'
COURSE_LIST = f'{LMS_DOMAIN}/api/v1/teaching/courses/'
auth_token = 'XXXXXXXXXX'
response = requests.get(COURSE_LIST, headers={'Authorization': f'Token {auth_token}'})
"""
Example response:
[
    {
        'id': 9,  # this is the course identifier, it can be used to get assignment list or students
        'name': 'Programming Fundamentals',
        'url': '/courses/2020-autumn/2.9-programming_basics/',
        'semester': {
            'id': 1,
            'index': 122,
            'year': 2020,
            'academic_year': 2020,
            'type': 'autumn'
        }
    },
    ...
]
"""
```

### Course Students List

```python
import requests

LMS_DOMAIN = 'http://csc.test'
course_id = 9
ENROLLMENT_LIST = f'{LMS_DOMAIN}/api/v1/teaching/courses/{course_id}/enrollments/'
auth_token = 'XXXXX'
response = requests.get(ENROLLMENT_LIST, headers={'Authorization': f'Token {auth_token}'})

"""
Example response
response.json()
[
    {
        'id': 20,  # student identifier, unique within the course
        'grade': 'not_graded',
        'studentGroupId': 1595,
        'student': {
            'id': 122,
            'firstName': 'Ivan',
            'lastName': 'Ivanov'
        },
        'studentProfileId': 12443
    },
    {
        'id': 205,
        'grade': 'not_graded',
        'studentGroupId': 1595,
        'student': {
            'id': 153,
            'firstName': 'Anton',
            'lastName': 'Antonov'
        },
        'studentProfileId': 12443
    },
    ...
]
"""
```

### ### Course Assignments List

```python
import requests

LMS_DOMAIN = 'http://csc.test'
course_id = 9
auth_token = 'XXXXXXX'
endpoint = f'{LMS_DOMAIN}/api/v1/teaching/courses/{course_id}/assignments/'
response = requests.get(endpoint, headers={'Authorization': f'Token {auth_token}'})
"""
[
    {
        "id": 2727,
        "deadlineAt": "2021-10-22T20:00:00Z",
        "title": "Homework #3",
        "passingScore": 2,
        "maximumScore": 5,
        "weight": "1.00",
        "ttc": null,
        "solutionFormat": "external"
    },
    {
        "id": 2728,
        "deadlineAt": "2021-10-22T20:00:00Z",
        "title": "Homework #3 (SPbSU)",
        "passingScore": 2,
        "maximumScore": 5,
        "weight": "1.00",
        "ttc": null,
        "solutionFormat": "external"
    },
    ...
]
"""
```

### Grade Assignment

FIXME: need to refactor endpoint to use enrollmentId (student identifier within the course) 
TODO: We can update assignment grade using put/patch methods, sending json. On success returns 200 status code, 400 - if validation error 
TODO: Add example with validation error

```python
import requests

LMS_DOMAIN = 'http://csc.test'
course_id = 9
assignment_id = 2727
enrollment_id = 20
auth_token = 'XXXXXXX'
endpoint = f'{LMS_DOMAIN}/api/v1/teaching/courses/{course_id}/assignments/{assignment_id}/students/{enrollment_id}/'
response = requests.put(endpoint, json={'score': '2'}, headers={'Authorization': f'Token {auth_token}'})
assert response.status_code == 200
"""
Example successful response:
{'pk': 956, 'score': '2.00', 'state': 'pass', 'student_id': 122}
"""
```
