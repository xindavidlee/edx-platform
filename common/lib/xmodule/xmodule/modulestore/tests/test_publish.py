"""
Test the publish code (mostly testing that publishing doesn't result in orphans)
"""
import unittest
import ddt
import itertools
from shutil import rmtree
from tempfile import mkdtemp
from nose.plugins.attrib import attr
from nose.tools import (                        # pylint: disable=W0611,E0611
    assert_true, assert_false,
    assert_equals, assert_not_equals,
    assert_is, assert_is_not,
    assert_is_instance, assert_is_none,
    assert_in, assert_not_in,
    assert_raises, assert_raises_regexp,
)
from contextlib import contextmanager

from opaque_keys.edx.locator import CourseLocator
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.exceptions import ItemNotFoundError
from xmodule.modulestore.xml_exporter import export_course_to_xml
from xmodule.modulestore.tests.test_split_w_old_mongo import SplitWMongoCourseBootstrapper
from xmodule.modulestore.tests.factories import check_mongo_calls, mongo_uses_error_check
from xmodule.modulestore.tests.test_cross_modulestore_import_export import (
    MongoContentstoreBuilder, MODULESTORE_SETUPS,
    DRAFT_MODULESTORE_SETUP, SPLIT_MODULESTORE_SETUP, MongoModulestoreBuilder
)


@attr('mongo')
class TestPublish(SplitWMongoCourseBootstrapper):
    """
    Test the publish code (primary causing orphans)
    """
    def _create_course(self):
        """
        Create the course, publish all verticals
        * some detached items
        """
        # There are 12 created items and 7 parent updates
        # create course: finds: 1 to verify uniqueness, 1 to find parents
        # sends: 1 to create course, 1 to create overview
        with check_mongo_calls(4, 2):
            super(TestPublish, self)._create_course(split=False)  # 2 inserts (course and overview)

        # with bulk will delay all inheritance computations which won't be added into the mongo_calls
        with self.draft_mongo.bulk_operations(self.old_course_key):
            # finds: 1 for parent to add child and 2 to get ancestors
            # sends: 1 for insert, 1 for parent (add child)
            with check_mongo_calls(3, 2):
                self._create_item('chapter', 'Chapter1', {}, {'display_name': 'Chapter 1'}, 'course', 'runid', split=False)

            with check_mongo_calls(4, 2):
                self._create_item('chapter', 'Chapter2', {}, {'display_name': 'Chapter 2'}, 'course', 'runid', split=False)
            # For each vertical (2) created:
            #   - load draft
            #   - load non-draft
            #   - get last error
            #   - load parent
            #   - get ancestors
            #   - load inheritable data
            with check_mongo_calls(15, 6):
                self._create_item('vertical', 'Vert1', {}, {'display_name': 'Vertical 1'}, 'chapter', 'Chapter1', split=False)
                self._create_item('vertical', 'Vert2', {}, {'display_name': 'Vertical 2'}, 'chapter', 'Chapter1', split=False)
            # For each (4) item created
            #   - try to find draft
            #   - try to find non-draft
            #   - compute what is parent
            #   - load draft parent again & compute its parent chain up to course
            # count for updates increased to 16 b/c of edit_info updating
            with check_mongo_calls(36, 16):
                self._create_item('html', 'Html1', "<p>Goodbye</p>", {'display_name': 'Parented Html'}, 'vertical', 'Vert1', split=False)
                self._create_item(
                    'discussion', 'Discussion1',
                    "discussion discussion_category=\"Lecture 1\" discussion_id=\"a08bfd89b2aa40fa81f2c650a9332846\" discussion_target=\"Lecture 1\"/>\n",
                    {
                        "discussion_category": "Lecture 1",
                        "discussion_target": "Lecture 1",
                        "display_name": "Lecture 1 Discussion",
                        "discussion_id": "a08bfd89b2aa40fa81f2c650a9332846"
                    },
                    'vertical', 'Vert1',
                    split=False
                )
                self._create_item('html', 'Html2', "<p>Hello</p>", {'display_name': 'Hollow Html'}, 'vertical', 'Vert1', split=False)
                self._create_item(
                    'discussion', 'Discussion2',
                    "discussion discussion_category=\"Lecture 2\" discussion_id=\"b08bfd89b2aa40fa81f2c650a9332846\" discussion_target=\"Lecture 2\"/>\n",
                    {
                        "discussion_category": "Lecture 2",
                        "discussion_target": "Lecture 2",
                        "display_name": "Lecture 2 Discussion",
                        "discussion_id": "b08bfd89b2aa40fa81f2c650a9332846"
                    },
                    'vertical', 'Vert2',
                    split=False
                )

            with check_mongo_calls(2, 2):
                # 2 finds b/c looking for non-existent parents
                self._create_item('static_tab', 'staticuno', "<p>tab</p>", {'display_name': 'Tab uno'}, None, None, split=False)
                self._create_item('course_info', 'updates', "<ol><li><h2>Sep 22</h2><p>test</p></li></ol>", {}, None, None, split=False)

    def test_publish_draft_delete(self):
        """
        To reproduce a bug (STUD-811) publish a vertical, convert to draft, delete a child, move a child, publish.
        See if deleted and moved children still is connected or exists in db (bug was disconnected but existed)
        """
        vert_location = self.old_course_key.make_usage_key('vertical', block_id='Vert1')
        item = self.draft_mongo.get_item(vert_location, 2)
        # Finds:
        #   1 get draft vert,
        #   2 compute parent
        #   3-14 for each child: (3 children x 4 queries each)
        #      get draft, compute parent, and then published child
        #      compute inheritance
        #   15 get published vert
        #   16-18 get ancestor chain
        #   19 compute inheritance
        #   20-22 get draft and published vert, compute parent
        # Sends:
        #   delete the subtree of drafts (1 call),
        #   update the published version of each node in subtree (4 calls),
        #   update the ancestors up to course (2 calls)
        if mongo_uses_error_check(self.draft_mongo):
            max_find = 23
        else:
            max_find = 22
        with check_mongo_calls(max_find, 7):
            self.draft_mongo.publish(item.location, self.user_id)

        # verify status
        item = self.draft_mongo.get_item(vert_location, 0)
        self.assertFalse(getattr(item, 'is_draft', False), "Item was published. Draft should not exist")
        # however, children are still draft, but I'm not sure that's by design

        # delete the draft version of the discussion
        location = self.old_course_key.make_usage_key('discussion', block_id='Discussion1')
        self.draft_mongo.delete_item(location, self.user_id)

        draft_vert = self.draft_mongo.get_item(vert_location, 0)
        self.assertTrue(getattr(draft_vert, 'is_draft', False), "Deletion didn't convert parent to draft")
        self.assertNotIn(location, draft_vert.children)
        # move the other child
        other_child_loc = self.old_course_key.make_usage_key('html', block_id='Html2')
        draft_vert.children.remove(other_child_loc)
        other_vert = self.draft_mongo.get_item(self.old_course_key.make_usage_key('vertical', block_id='Vert2'), 0)
        other_vert.children.append(other_child_loc)
        self.draft_mongo.update_item(draft_vert, self.user_id)
        self.draft_mongo.update_item(other_vert, self.user_id)
        # publish
        self.draft_mongo.publish(vert_location, self.user_id)
        item = self.draft_mongo.get_item(draft_vert.location, revision=ModuleStoreEnum.RevisionOption.published_only)
        self.assertNotIn(location, item.children)
        self.assertIsNone(self.draft_mongo.get_parent_location(location))
        with self.assertRaises(ItemNotFoundError):
            self.draft_mongo.get_item(location)
        self.assertNotIn(other_child_loc, item.children)
        self.assertTrue(self.draft_mongo.has_item(other_child_loc), "Oops, lost moved item")


class MixedMongoModulestoreTest(object):
    modulestore_builder = DRAFT_MODULESTORE_SETUP


class MixedSplitModulestoreTest(object):
    modulestore_builder = SPLIT_MODULESTORE_SETUP


class DirectMongoModulestoreTest(object):
    modulestore_builder = MongoModulestoreBuilder()


class UniversalTestSetup(object):
    """
    This class exists to test XML import and export between different modulestore
    classes.

    Requires from subclasses:
        self.modulestore - modulestore to be tested
        self.course_key - course key of the test course
    """

    def _create_course(self, store, course_key):
        """
        Create the course that'll be published below. The course has a binary structure, meaning:
        The course has two chapters (chapter_0 & chapter_1), each of which has two sequentials (seqential_0/1 & sequential_2/3),
        each of which has two verticals (vertical_0/1 - vertical_6/7), each of which has two units (unit_0/1 - unit_14/15).
        """
        def _create_chapter(parent, block_id):
            return store.create_child(
                self.user_id, parent.location, 'chapter', block_id=block_id
            )

        def _create_seq(parent, block_id):
            return store.create_child(
                self.user_id, parent.location, 'sequential', block_id=block_id
            )

        def _create_vert(parent, block_id):
            return store.create_child(
                self.user_id, parent.location, 'vertical', block_id=block_id
            )

        def _create_unit(parent, block_id):
            return store.create_child(
                self.user_id, parent.location, 'html', block_id=block_id
            )

        # Create course.
        self.course = store.create_course(course_key.org, course_key.course, course_key.run, self.user_id)

        # Create chapters.
        for idx in xrange(0, 2):
            setattr(self, 'chapter{}'.format(idx), _create_chapter(self.course, 'chapter_{}'.format(idx)))

        # Create sequentials.
        for idx in xrange(0, 4):
            chapter_idx = idx / 2
            setattr(self, 'seq{}'.format(idx), _create_seq(getattr(self, 'chapter{}'.format(chapter_idx)), 'sequential_{}'.format(idx)))

        # Create verticals.
        for idx in xrange(0, 8):
            seq_idx = idx / 2
            setattr(self, 'vertical{}'.format(idx), _create_vert(getattr(self, 'seq{}'.format(seq_idx)), 'vertical_{}'.format(idx)))

        # Create units.
        for idx in xrange(0, 16):
            vert_idx = idx / 2
            setattr(self, 'unit{}'.format(idx), _create_unit(getattr(self, 'vertical{}'.format(vert_idx)), 'unit_{}'.format(idx)))

    def setUp(self):
        self.user_id = -3
        self.course_key = CourseLocator('test_org', 'test_course', 'test_run')


@contextmanager
def create_export_dir():
    try:
        export_dir = mkdtemp()
        yield export_dir
    finally:
        rmtree(export_dir, ignore_errors=True)


class OLXFormatChecker(object):
    def check_olx_format(self, root_dir, course_dir, check_info):
        pass


class UniversalTestProcedure(OLXFormatChecker, UniversalTestSetup):

    EXPORTED_COURSE_BEFORE_DIR_NAME = 'exported_course_before'
    EXPORTED_COURSE_AFTER_DIR_NAME = 'exported_course_after'

    def test_elemental_operation(self):
        with create_export_dir() as export_dir:
            # Construct the contentstore for storing the first import
            with MongoContentstoreBuilder().build() as test_content:
                # Construct the modulestore for storing the first import (using the previously created contentstore)
                with self.modulestore_builder.build(contentstore=test_content) as test_modulestore:

                    # Create the course.
                    self._create_course(test_modulestore, self.course_key)

                    # Export the course.
                    export_course_to_xml(
                        test_modulestore,
                        test_content,
                        self.course_key,
                        export_dir,
                        self.EXPORTED_COURSE_BEFORE_DIR_NAME,
                    )
                    # Verify the export OLX format.
                    self.check_olx_format(export_dir, self.EXPORTED_COURSE_BEFORE_DIR_NAME, self.olx_loc_and_fmt_before)

                    # Get the specified test item.
                    with test_modulestore.branch_setting(ModuleStoreEnum.Branch.draft_preferred):
                        test_item = test_modulestore.get_item(self.course_key.make_usage_key(block_type=self.block_type, block_id=self.block_id))

                    # Perform an elemental operation on a particular item.
                    assert_true(hasattr(test_modulestore, self.operation))
                    elemental_op = getattr(test_modulestore, self.operation)
                    op_params = []
                    for p in self.operation_params:
                        if isinstance(p, basestring):
                            if p == '@location':
                                op_params.append(test_item.location)
                            elif p == '@user_id':
                                op_params.append(self.user_id)
                            else:
                                op_params.append(p)
                        else:
                            op_params.append(p)
                    elemental_op(*op_params)

                    # Export the course again.
                    export_course_to_xml(
                        test_modulestore,
                        test_content,
                        self.course_key,
                        export_dir,
                        self.EXPORTED_COURSE_AFTER_DIR_NAME,
                    )
                    # Verify the export OLX format.
                    self.check_olx_format(export_dir, self.EXPORTED_COURSE_AFTER_DIR_NAME, self.olx_loc_and_fmt_after)


class TestPublishSingleUnit(UniversalTestProcedure):
    __test__ = False
    block_type = 'html'
    block_id = 'unit_0'
    operation = 'publish'
    operation_params = ('@location', '@user_id')
    olx_loc_and_fmt_before = (
        # Used to check the export before the operation takes place.
        # List of:
        #   - path to OLX to check
        #   - matching OLX
        (
            ('drafts', 'html', 'unit_0.xml'),
            '''
            <html filename="html_unit"/>
            '''
        ),
        (
            ('html', 'unit_0.xml'),
            None,
        ),
    )
    olx_loc_and_fmt_after = (
        (
            ('drafts', 'html', 'unit_0.xml'),
            None, # None means the file/section shouldn't exist.
        ),
        (
            ('html', 'unit_0.xml'),
            '''
            <html filename="html_unit"/>
            '''
        ),
    )


for modulestore_backend in (
    MixedMongoModulestoreTest,
    MixedSplitModulestoreTest,
    DirectMongoModulestoreTest,
):
    for base_test_case in (
            TestPublishSingleUnit,
    ):

        test_name = base_test_case.__name__ + "With" + modulestore_backend.__name__
        test_classes = (base_test_case, modulestore_backend)
        vars()[test_name] = type(test_name, test_classes, {'__test__': True})

# If we don't delete the loop variables, then they leak into the global namespace
# and cause the last class looped through to be tested twice.
# pylint: disable=W0631
del modulestore_backend
del base_test_case


