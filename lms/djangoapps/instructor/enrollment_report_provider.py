"""
Abstract interface for Detailed Enrollment Report Provider
"""
import abc


class EnrollmentReportProvider(object):
    """
    Concrete MySQL implementation of the abstract base class (interface)
    """
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def get_enrollment_info(self, user, course_id):
        """
        Returns the User Enrollment information.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_user_profile(self, user_id):
        """
        Returns the UserProfile information.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_payment_info(self, user, course_id):
        """
        Returns the User Payment information.
        """
        raise NotImplementedError()
