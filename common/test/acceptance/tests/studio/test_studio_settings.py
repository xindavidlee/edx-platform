"""
Acceptance tests for Studio's Setting pages
"""

from base_studio_test import StudioCourseTest
from bok_choy.promise import EmptyPromise
from ...fixtures.course import XBlockFixtureDesc
from ..helpers import create_user_partition_json
from ...pages.studio.overview import CourseOutlinePage
from ...pages.studio.settings_advanced import AdvancedSettingsPage
from ...pages.studio.settings_group_configurations import GroupConfigurationsPage
from ...pages.studio.settings_certificates import CertificatesPage
from unittest import skip
from textwrap import dedent
from xmodule.partitions.partitions import Group


class ContentGroupConfigurationTest(StudioCourseTest):
    """
    Tests for content groups in the Group Configurations Page.
    There are tests for the experiment groups in test_studio_split_test.
    """
    def setUp(self):
        super(ContentGroupConfigurationTest, self).setUp()
        self.group_configurations_page = GroupConfigurationsPage(
            self.browser,
            self.course_info['org'],
            self.course_info['number'],
            self.course_info['run']
        )

        self.outline_page = CourseOutlinePage(
            self.browser,
            self.course_info['org'],
            self.course_info['number'],
            self.course_info['run']
        )

    def populate_course_fixture(self, course_fixture):
        """
        Populates test course with chapter, sequential, and 1 problems.
        The problem is visible only to Group "alpha".
        """
        course_fixture.add_children(
            XBlockFixtureDesc('chapter', 'Test Section').add_children(
                XBlockFixtureDesc('sequential', 'Test Subsection').add_children(
                    XBlockFixtureDesc('vertical', 'Test Unit')
                )
            )
        )

    def create_and_verify_content_group(self, name, existing_groups):
        """
        Creates a new content group and verifies that it was properly created.
        """
        self.assertEqual(existing_groups, len(self.group_configurations_page.content_groups))
        if existing_groups == 0:
            self.group_configurations_page.create_first_content_group()
        else:
            self.group_configurations_page.add_content_group()
        config = self.group_configurations_page.content_groups[existing_groups]
        config.name = name
        # Save the content group
        self.assertEqual(config.get_text('.action-primary'), "Create")
        self.assertFalse(config.delete_button_is_present)
        config.save()
        self.assertIn(name, config.name)
        return config

    def test_no_content_groups_by_default(self):
        """
        Scenario: Ensure that message telling me to create a new content group is
            shown when no content groups exist.
        Given I have a course without content groups
        When I go to the Group Configuration page in Studio
        Then I see "You have not created any content groups yet." message
        """
        self.group_configurations_page.visit()
        self.assertTrue(self.group_configurations_page.no_content_groups_message_is_present)
        self.assertIn(
            "You have not created any content groups yet.",
            self.group_configurations_page.no_content_groups_message_text
        )

    def test_can_create_and_edit_content_groups(self):
        """
        Scenario: Ensure that the content groups can be created and edited correctly.
        Given I have a course without content groups
        When I click button 'Add your first Content Group'
        And I set new the name and click the button 'Create'
        Then I see the new content is added and has correct data
        And I click 'New Content Group' button
        And I set the name and click the button 'Create'
        Then I see the second content group is added and has correct data
        When I edit the second content group
        And I change the name and click the button 'Save'
        Then I see the second content group is saved successfully and has the new name
        """
        self.group_configurations_page.visit()
        self.create_and_verify_content_group("New Content Group", 0)
        second_config = self.create_and_verify_content_group("Second Content Group", 1)

        # Edit the second content group
        second_config.edit()
        second_config.name = "Updated Second Content Group"
        self.assertEqual(second_config.get_text('.action-primary'), "Save")
        second_config.save()

        self.assertIn("Updated Second Content Group", second_config.name)

    def test_cannot_delete_used_content_group(self):
        """
        Scenario: Ensure that the user cannot delete used content group.
        Given I have a course with 1 Content Group
        And I go to the Group Configuration page
        When I try to delete the Content Group with name "New Content Group"
        Then I see the delete button is disabled.
        """
        self.course_fixture._update_xblock(self.course_fixture._course_location, {
            "metadata": {
                u"user_partitions": [
                    create_user_partition_json(
                        0,
                        'Configuration alpha,',
                        'Content Group Partition',
                        [Group("0", 'alpha')],
                        scheme="cohort"
                    )
                ],
            },
        })
        problem_data = dedent("""
            <problem markdown="Simple Problem" max_attempts="" weight="">
              <p>Choose Yes.</p>
              <choiceresponse>
                <checkboxgroup direction="vertical">
                  <choice correct="true">Yes</choice>
                </checkboxgroup>
              </choiceresponse>
            </problem>
        """)
        vertical = self.course_fixture.get_nested_xblocks(category="vertical")[0]
        self.course_fixture.create_xblock(
            vertical.locator,
            XBlockFixtureDesc('problem', "VISIBLE TO ALPHA", data=problem_data, metadata={"group_access": {0: [0]}}),
        )
        self.group_configurations_page.visit()
        config = self.group_configurations_page.content_groups[0]
        self.assertTrue(config.delete_button_is_disabled)

    def test_can_delete_unused_content_group(self):
        """
        Scenario: Ensure that the user can delete unused content group.
        Given I have a course with 1 Content Group
        And I go to the Group Configuration page
        When I delete the Content Group with name "New Content Group"
        Then I see that there is no Content Group
        When I refresh the page
        Then I see that the content group has been deleted
        """
        self.group_configurations_page.visit()
        config = self.create_and_verify_content_group("New Content Group", 0)
        self.assertTrue(config.delete_button_is_present)

        self.assertEqual(len(self.group_configurations_page.content_groups), 1)

        # Delete content group
        config.delete()
        self.assertEqual(len(self.group_configurations_page.content_groups), 0)

        self.group_configurations_page.visit()
        self.assertEqual(len(self.group_configurations_page.content_groups), 0)

    def test_must_supply_name(self):
        """
        Scenario: Ensure that validation of the content group works correctly.
        Given I have a course without content groups
        And I create new content group without specifying a name click the button 'Create'
        Then I see error message "Content Group name is required."
        When I set a name and click the button 'Create'
        Then I see the content group is saved successfully
        """
        self.group_configurations_page.visit()
        self.group_configurations_page.create_first_content_group()
        config = self.group_configurations_page.content_groups[0]
        config.save()
        self.assertEqual(config.mode, 'edit')
        self.assertEqual("Group name is required", config.validation_message)
        config.name = "Content Group Name"
        config.save()
        self.assertIn("Content Group Name", config.name)

    def test_can_cancel_creation_of_content_group(self):
        """
        Scenario: Ensure that creation of a content group can be canceled correctly.
        Given I have a course without content groups
        When I click button 'Add your first Content Group'
        And I set new the name and click the button 'Cancel'
        Then I see that there is no content groups in the course
        """
        self.group_configurations_page.visit()
        self.group_configurations_page.create_first_content_group()
        config = self.group_configurations_page.content_groups[0]
        config.name = "Content Group"
        config.cancel()
        self.assertEqual(0, len(self.group_configurations_page.content_groups))

    def test_content_group_empty_usage(self):
        """
        Scenario: When content group is not used, ensure that the link to outline page works correctly.
        Given I have a course without content group
        And I create new content group
        Then I see a link to the outline page
        When I click on the outline link
        Then I see the outline page
        """
        self.group_configurations_page.visit()
        config = self.create_and_verify_content_group("New Content Group", 0)
        config.toggle()
        config.click_outline_anchor()

        # Waiting for the page load and verify that we've landed on course outline page
        EmptyPromise(
            lambda: self.outline_page.is_browser_on_page(), "loaded page {!r}".format(self.outline_page),
            timeout=30
        ).fulfill()


class AdvancedSettingsValidationTest(StudioCourseTest):
    """
    Tests for validation feature in Studio's advanced settings tab
    """
    def setUp(self):
        super(AdvancedSettingsValidationTest, self).setUp()
        self.advanced_settings = AdvancedSettingsPage(
            self.browser,
            self.course_info['org'],
            self.course_info['number'],
            self.course_info['run']
        )

        self.type_fields = ['Course Display Name', 'Advanced Module List', 'Discussion Topic Mapping',
                            'Maximum Attempts', 'Course Announcement Date']

        # Before every test, make sure to visit the page first
        self.advanced_settings.visit()
        self.assertTrue(self.advanced_settings.is_browser_on_page())

    def test_modal_shows_one_validation_error(self):
        """
        Test that advanced settings don't save if there's a single wrong input,
        and that it shows the correct error message in the modal.
        """

        # Feed an integer value for String field.
        # .set method saves automatically after setting a value
        course_display_name = self.advanced_settings.get('Course Display Name')
        self.advanced_settings.set('Course Display Name', 1)
        self.advanced_settings.wait_for_modal_load()

        # Test Modal
        self.check_modal_shows_correct_contents(['Course Display Name'])
        self.advanced_settings.refresh_and_wait_for_load()

        self.assertEquals(
            self.advanced_settings.get('Course Display Name'),
            course_display_name,
            'Wrong input for Course Display Name must not change its value'
        )

    def test_modal_shows_multiple_validation_errors(self):
        """
        Test that advanced settings don't save with multiple wrong inputs
        """

        # Save original values and feed wrong inputs
        original_values_map = self.get_settings_fields_of_each_type()
        self.set_wrong_inputs_to_fields()
        self.advanced_settings.wait_for_modal_load()

        # Test Modal
        self.check_modal_shows_correct_contents(self.type_fields)
        self.advanced_settings.refresh_and_wait_for_load()

        for key, val in original_values_map.iteritems():
            self.assertEquals(
                self.advanced_settings.get(key),
                val,
                'Wrong input for Advanced Settings Fields must not change its value'
            )

    def test_undo_changes(self):
        """
        Test that undo changes button in the modal resets all settings changes
        """

        # Save original values and feed wrong inputs
        original_values_map = self.get_settings_fields_of_each_type()
        self.set_wrong_inputs_to_fields()

        # Let modal popup
        self.advanced_settings.wait_for_modal_load()

        # Press Undo Changes button
        self.advanced_settings.undo_changes_via_modal()

        # Check that changes are undone
        for key, val in original_values_map.iteritems():
            self.assertEquals(
                self.advanced_settings.get(key),
                val,
                'Undoing Should revert back to original value'
            )

    def test_manual_change(self):
        """
        Test that manual changes button in the modal keeps settings unchanged
        """
        inputs = {"Course Display Name": 1,
                  "Advanced Module List": 1,
                  "Discussion Topic Mapping": 1,
                  "Maximum Attempts": '"string"',
                  "Course Announcement Date": '"string"',
                  }

        self.set_wrong_inputs_to_fields()
        self.advanced_settings.wait_for_modal_load()
        self.advanced_settings.trigger_manual_changes()

        # Check that the validation modal went away.
        self.assertFalse(self.advanced_settings.is_validation_modal_present())

        # Iterate through the wrong values and make sure they're still displayed
        for key, val in inputs.iteritems():
            print self.advanced_settings.get(key)
            print val
            self.assertEquals(
                str(self.advanced_settings.get(key)),
                str(val),
                'manual change should keep: ' + str(val) + ', but is: ' + str(self.advanced_settings.get(key))
            )

    def check_modal_shows_correct_contents(self, wrong_settings_list):
        """
        Helper function that checks if the validation modal contains correct
        error messages.
        """
        # Check presence of modal
        self.assertTrue(self.advanced_settings.is_validation_modal_present())

        # List of wrong settings item & what is presented in the modal should be the same
        error_item_names = self.advanced_settings.get_error_item_names()
        self.assertEqual(set(wrong_settings_list), set(error_item_names))

        error_item_messages = self.advanced_settings.get_error_item_messages()
        self.assertEqual(len(error_item_names), len(error_item_messages))

    def get_settings_fields_of_each_type(self):
        """
        Get one of each field type:
           - String: Course Display Name
           - List: Advanced Module List
           - Dict: Discussion Topic Mapping
           - Integer: Maximum Attempts
           - Date: Course Announcement Date
        """
        return {
            "Course Display Name": self.advanced_settings.get('Course Display Name'),
            "Advanced Module List": self.advanced_settings.get('Advanced Module List'),
            "Discussion Topic Mapping": self.advanced_settings.get('Discussion Topic Mapping'),
            "Maximum Attempts": self.advanced_settings.get('Maximum Attempts'),
            "Course Announcement Date": self.advanced_settings.get('Course Announcement Date'),
        }

    def set_wrong_inputs_to_fields(self):
        """
        Set wrong values for the chosen fields
        """
        self.advanced_settings.set_values(
            {
                "Course Display Name": 1,
                "Advanced Module List": 1,
                "Discussion Topic Mapping": 1,
                "Maximum Attempts": '"string"',
                "Course Announcement Date": '"string"',
            }
        )

    def test_only_expected_fields_are_displayed(self):
        """
        Scenario: The Advanced Settings screen displays settings/fields not specifically hidden from
        view by a developer.
        Given I have a set of CourseMetadata fields defined for the course
        When I view the Advanced Settings screen for the course
        The total number of fields displayed matches the number I expect
        And the actual fields displayed match the fields I expect to see
        """
        expected_fields = self.advanced_settings.expected_settings_names
        displayed_fields = self.advanced_settings.displayed_settings_names
        self.assertEquals(set(displayed_fields), set(expected_fields))


class CertificatesTest(StudioCourseTest):
    """
    Tests for settings/certificates Page.
    """
    def setUp(self, is_staff=False):
        super(CertificatesTest, self).setUp(is_staff)
        self.certificates_page = CertificatesPage(
            self.browser,
            self.course_info['org'],
            self.course_info['number'],
            self.course_info['run']
        )

    def make_signatory_data(self, prefix='First'):
        """
        Makes signatory dict which can be used in the tests to create certificates
        """
        return {
            'name': '{prefix} Signatory Name'.format(prefix=prefix),
            'title': '{prefix} Signatory Title'.format(prefix=prefix),
            'organization': '{prefix} Signatory Organization'.format(prefix=prefix),
        }

    def create_and_verify_certificate(self, name, description, existing_certs, signatories):
        """
        Creates a new certificate and verifies that it was properly created.
        """
        self.assertEqual(existing_certs, len(self.certificates_page.certificates))
        if existing_certs == 0:
            self.certificates_page.create_first_certificate()
        else:
            self.certificates_page.add_certificate()
        certificate = self.certificates_page.certificates[existing_certs]
        certificate.name = name
        certificate.description = description

        # add signatories
        added_signatories = 0
        for idx, signatory in enumerate(signatories):
            certificate.signatories[idx].name = signatory['name']
            certificate.signatories[idx].title = signatory['title']
            certificate.signatories[idx].organization = signatory['organization']

            added_signatories += 1
            if len(signatories) > added_signatories:
                certificate.add_signatory()

        # Save the certificate
        self.assertEqual(certificate.get_text('.action-primary'), "Create")
        self.assertFalse(certificate.delete_button_is_present)
        certificate.save()
        self.assertIn(name, certificate.name)
        return certificate

    def test_no_certificates_by_default(self):
        """
        Scenario: Ensure that message telling me to create a new certificate is
            shown when no certificate exist.
        Given I have a course without certificates
        When I go to the Certificates page in Studio
        Then I see "You have not created any certificates yet." message
        """
        self.certificates_page.visit()
        self.assertTrue(self.certificates_page.no_certificates_message_shown)
        self.assertIn(
            "You have not created any certificates yet.",
            self.certificates_page.no_certificates_message_text
        )

    def test_can_create_and_edit_certficates(self):
        """
        Scenario: Ensure that the certificates can be created and edited correctly.
        Given I have a course without certificates
        When I click button 'Add your first Certificate'
        And I set new the name, description and two signatories and click the button 'Create'
        Then I see the new certificate is added and has correct data
        And I click 'New Certificate' button
        And I set the name and click the button 'Create'
        Then I see the second certificate is added and has correct data
        When I edit the second certificate
        And I change the name and click the button 'Save'
        Then I see the second certificate is saved successfully and has the new name
        """
        self.certificates_page.visit()
        self.create_and_verify_certificate(
            "New Certificate",
            "Description of first certificate",
            0,
            [self.make_signatory_data('first'), self.make_signatory_data('second')]
        )
        second_certificate = self.create_and_verify_certificate(
            "Second Certificate",
            "Description of first certificate",
            1,
            [self.make_signatory_data('third'), self.make_signatory_data('forth')]
        )

        # Edit the second certificate
        second_certificate.edit()
        second_certificate.name = "Updated Second Certificate"
        self.assertEqual(second_certificate.get_text('.action-primary'), "Save")
        second_certificate.save()

        self.assertIn("Updated Second Certificate", second_certificate.name)

    def test_can_delete_certificate(self):
        """
        Scenario: Ensure that the user can delete certificate.
        Given I have a course with 1 certificate
        And I go to the Certificates page
        When I delete the Certificate with name "New Certificate"
        Then I see that there is no certificate
        When I refresh the page
        Then I see that the certificate has been deleted
        """
        self.certificates_page.visit()
        certificate = self.create_and_verify_certificate(
            "New Certificate",
            "Description of first certificate",
            0,
            [self.make_signatory_data('first'), self.make_signatory_data('second')]
        )

        self.assertTrue(certificate.delete_button_is_present)

        self.assertEqual(len(self.certificates_page.certificates), 1)

        # Delete certificate
        certificate.delete_certificate()

        self.certificates_page.visit()
        self.assertEqual(len(self.certificates_page.certificates), 0)

    def test_can_create_and_edit_signatories_of_certficate(self):
        """
        Scenario: Ensure that the certificates can be created with signatories and edited correctly.
        Given I have a course without certificates
        When I click button 'Add your first Certificate'
        And I set new the name, description and signatory and click the button 'Create'
        Then I see the new certificate is added and has one signatory inside it
        When I click 'Edit' button of signatory panel
        And I set the name and click the button 'Save' icon
        Then I see the signatory name updated with newly set name
        When I refresh the certificates page
        Then I can see course has one certificate with new signatory name
        When I click 'Edit' button of signatory panel
        And click on 'Close' button
        Then I can see no change in signatory detail
        """
        self.certificates_page.visit()
        certificate = self.create_and_verify_certificate(
            "New Certificate",
            "Description of first certificate",
            0,
            [self.make_signatory_data('first')]
        )
        self.assertEqual(len(self.certificates_page.certificates), 1)
        # Edit the signatory in certificate
        signatory = certificate.signatories[0]
        signatory.edit()

        signatory.name = 'Updated signatory name'
        signatory.title = 'Update signatory title'
        signatory.organization = 'Updated signatory organization'
        signatory.save()

        self.assertEqual(len(self.certificates_page.certificates), 1)

        signatory = self.certificates_page.certificates[0].signatories[0]
        self.assertIn("Updated signatory name", signatory.name)
        self.assertIn("Update signatory title", signatory.title)
        self.assertIn("Updated signatory organization", signatory.organization)

        signatory.edit()
        signatory.close()

        self.assertIn("Updated signatory name", signatory.name)

    def test_must_supply_certificate_name(self):
        """
        Scenario: Ensure that validation of the certificates works correctly.
        Given I have a course without certificates
        And I create new certificate without specifying a name click the button 'Create'
        Then I see error message "Certificate name is required."
        When I set a name and click the button 'Create'
        Then I see the certificate is saved successfully
        """
        self.certificates_page.visit()
        self.certificates_page.create_first_certificate()
        certificate = self.certificates_page.certificates[0]
        certificate.name = ""
        certificate.save()
        self.assertEqual(certificate.mode, 'edit')
        self.assertEqual("Certificate name is required.", certificate.validation_message)
        certificate.name = "First Certificate Name"
        certificate.save()
        self.assertIn("First Certificate Name", certificate.name)

    def test_can_cancel_creation_of_certificate(self):
        """
        Scenario: Ensure that creation of a certificate can be canceled correctly.
        Given I have a course without certificates
        When I click button 'Add your first Certificate'
        And I set name of certificate and click the button 'Cancel'
        Then I see that there is no certificates in the course
        """
        self.certificates_page.visit()
        self.certificates_page.create_first_certificate()
        certificate = self.certificates_page.certificates[0]
        certificate.name = "First Certificate Name"
        certificate.cancel()
        self.assertEqual(len(self.certificates_page.certificates), 0)
