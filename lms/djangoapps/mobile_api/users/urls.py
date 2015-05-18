"""
URLs for user API
"""
from django.conf.urls import patterns, url
from django.conf import settings

from .views import UserDetail, UserCourseEnrollmentsList, UserCourseStatus

import time

import os

USERNAME_PATTERN = r'(?P<username>[\w.+-]+)'

def log_exec_time(fn):
    t1 = time.time()
    os.system('echo Calling... >> /edx/app/edxapp/edx-platform/test.log')
    res = fn()
    dbstr = 'total time: ' + str(time.time() - t1)
    os.system('echo "' + dbstr + '" >> /edx/app/edxapp/edx-platform/test.log')
    os.system('echo >> /edx/app/edxapp/edx-platform/test.log')
    return res


urlpatterns = patterns(
    'mobile_api.users.views',
    url('^' + USERNAME_PATTERN + '$', UserDetail.as_view(), name='user-detail'),
    url(
        '^' + USERNAME_PATTERN + '/course_enrollments/$',
        log_exec_time(UserCourseEnrollmentsList.as_view),
        name='courseenrollment-detail'
    ),
    url('^{}/course_status_info/{}'.format(USERNAME_PATTERN, settings.COURSE_ID_PATTERN),
        UserCourseStatus.as_view(),
        name='user-course-status')
)
