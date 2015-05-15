"""
Test the publish code (mostly testing that publishing doesn't result in orphans)
"""
import os
import re
import unittest
import ddt
import uuid
from shutil import rmtree
from tempfile import mkdtemp
from nose.plugins.attrib import attr
from contextlib import contextmanager
import xml.etree.ElementTree as ET

from opaque_keys.edx.locator import CourseLocator
from xmodule.exceptions import InvalidVersionError
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


class UniversalTestSetup(unittest.TestCase):
    """
    This class exists to test XML import and export between different modulestore
    classes.

    Requires from subclasses:
        self.user_id - fake user_id
    """

    def _create_course(self, store, course_key):
        """
        Create the course that'll be published below. The course has a binary structure, meaning:
        The course has two chapters (chapter_0 & chapter_1),
        each of which has two sequentials (sequential_0/1 & sequential_2/3),
        each of which has two verticals (vertical_0/1 - vertical_6/7),
        each of which has two units (unit_0/1 - unit_14/15).
        """
        def _create_child(parent, block_type, block_id):
            """
            Create a child block within the course.
            """
            return store.create_child(
                self.user_id, parent.location, block_type, block_id=block_id
            )

        def _make_block_id(block_type, num):
            """
            Given a block_type/num, return a block id.
            """
            return '{}{:02d}'.format(block_type, num)

        def _make_course_db_entry(parent_type, parent_id, block_id, idx, child_block_type, child_block_id_base):
            """
            Make a single entry for the course DB.
            """
            return {
                'parent_type': parent_type,
                'parent_id': parent_id,
                'index_in_children_list': idx % 2,
                'filename': block_id,
                'child_ids': (
                    (child_block_type, _make_block_id(child_block_id_base, idx * 2)),
                    (child_block_type, _make_block_id(child_block_id_base, idx * 2 + 1)),
                )
            }

        # Create all the course items on the draft branch.
        with store.branch_setting(ModuleStoreEnum.Branch.draft_preferred):
            # Create course.
            self.course = store.create_course(course_key.org, course_key.course, course_key.run, self.user_id)

            # Create chapters.
            block_type = 'chapter'
            for idx in xrange(0, 2):
                parent_type = 'course'
                parent_id = 'course'
                block_id = _make_block_id(block_type, idx)
                setattr(self, block_id, _create_child(self.course, block_type, block_id))
                db_entry = {
                    (block_type, block_id): _make_course_db_entry(
                        parent_type, parent_id, block_id, idx, 'sequential', 'sequential'
                    )
                }
                self.course_db.update(db_entry)

            # Create sequentials.
            block_type = 'sequential'
            for idx in xrange(0, 4):
                parent_type = 'chapter'
                parent_id = _make_block_id(parent_type, idx / 2)
                parent_item = getattr(self, parent_id)
                block_id = _make_block_id(block_type, idx)
                setattr(self, block_id, _create_child(parent_item, block_type, block_id))
                db_entry = {
                    (block_type, block_id): _make_course_db_entry(
                        parent_type, parent_id, block_id, idx, 'vertical', 'vertical'
                    )
                }
                self.course_db.update(db_entry)

            # Create verticals.
            block_type = 'vertical'
            for idx in xrange(0, 8):
                parent_type = 'sequential'
                parent_id = _make_block_id(parent_type, idx / 2)
                parent_item = getattr(self, parent_id)
                block_id = _make_block_id(block_type, idx)
                setattr(self, block_id, _create_child(parent_item, block_type, block_id))
                db_entry = {
                    (block_type, block_id): _make_course_db_entry(
                        parent_type, parent_id, block_id, idx, 'html', 'unit'
                    )
                }
                self.course_db.update(db_entry)
                self.all_verticals.append((block_type, block_id))

            # Create html units.
            block_type = 'html'
            for idx in xrange(0, 16):
                parent_type = 'vertical'
                parent_id = _make_block_id(parent_type, idx / 2)
                parent_item = getattr(self, parent_id)
                block_id = _make_block_id('unit', idx)
                setattr(self, block_id, _create_child(parent_item, 'html', block_id))
                db_entry = {
                    (block_type, block_id): _make_course_db_entry(
                        parent_type, parent_id, block_id, idx, '', ''
                    )
                }
                self.course_db.update(db_entry)
                self.all_units.append((block_type, block_id))

    def setUp(self):
        self.user_id = -3
        self.course_key = CourseLocator('test_org', 'test_course', 'test_run')
        self.course = None

        # For convenience, maintain a list of (block_type, block_id) pairs for all verticals/units.
        self.all_verticals = []
        self.all_units = []

        # Course block database is keyed on (block_type, block_id) pairs.
        # It's built during the course creation below and contains all the parent/child
        # data needed to check the OLX.
        self.course_db = {}

        super(UniversalTestSetup, self).setUp()


class OLXFormatChecker(unittest.TestCase):
    """
    Examines the on-disk course export to verify that specific items are present/missing
    in the course export.
    Currently assumes that the course is broken up into different subdirs.

    Requires from subclasses:
        self.root_export_dir - absolute root directory of course exports
        self.export_dir - top-level course export directory name
    """
    unittest.TestCase.longMessage = True

    def _get_course_export_dir(self):
        """
        Ensure that the course has been exported and return course export dir.
        """
        block_path = os.path.join(self.root_export_dir, self.export_dir)  # pylint: disable=no-member
        self.assertTrue(
            os.path.isdir(block_path),
            msg='{} is not a dir.'.format(block_path)
        )
        return block_path

    def _get_block_type_path(self, course_export_dir, block_type, draft):
        """
        Return the path to the block type subdirectory, factoring in drafts.
        """
        block_path = course_export_dir
        if draft:
            block_path = os.path.join(block_path, 'drafts')
        return os.path.join(block_path, block_type)

    def _get_block_filename(self, block_id):
        """
        Return the course export filename for a block.
        """
        return '{}.xml'.format(block_id)

    def _get_block_contents(self, block_subdir_path, block_id):
        """
        Determine the filename containing the block info.
        Return the file contents.
        """
        block_file = self._get_block_filename(block_id)
        block_file_path = os.path.join(block_subdir_path, block_file)
        self.assertTrue(
            os.path.isfile(block_file_path),
            msg='{} is not an existing file.'.format(block_file_path)
        )
        with open(block_file_path, "r") as file_handle:
            return file_handle.read()

    def _assert_parsed_xml(self, block_contents, checklist):
        """
        Using a dictionary with the following format:
        {   'tag' : block_type,
            'attrs' : attrs,
            'children' : {
                'tag' : child_type,
                'attrs' : {'url_name' : child_id_regex},
            }
        }
        , verify the XML of a particular block in a course export.
        In the above dictionary, 'attrs' is a dict with {attribute:regex} pairs.
        """
        def _assert_xml_level(xml_root, tag, attrs, children):
            """
            Verify one level of the block XML. Called recursively to check other levels (children).
            """
            self.assertEqual(xml_root.tag, tag)
            if attrs:
                for attr_name, attr_re in attrs.iteritems():
                    if attr_re:
                        self.assertIn(attr_name, xml_root.attrib)
                        attr_re_comp = re.compile(attr_re)
                        self.assertIsNotNone(
                            attr_re_comp.search(xml_root.attrib[attr_name]),
                            msg='Attr {} of tag {} doesn\'t match regex of:\n{}'.format(
                                attr_name, tag, attr_re
                            )
                        )
            else:
                # If not checking the attrs, there should be *no* attrs in the XML.
                self.assertEqual(xml_root.attrib, {})
            if children:
                for child in xml_root:
                    _assert_xml_level(child, children['tag'], children.get('attrs'), children.get('children'))
            else:
                # If not checking the children, there should be *no* children in the XML.
                self.assertEqual([child for child in xml_root], [])

        # Parse the XML string into an ElementTree.
        block_tree = ET.fromstring(block_contents)
        # Now go through and verify the individual tags/attributes/children.
        _assert_xml_level(block_tree, checklist['tag'], checklist.get('attrs'), checklist.get('children'))

    def assertOLXContent(self, block_type, block_id, **kwargs):
        """
        Assert that a particular block exists in a course export in the proper draft/published location
        and that the format is correct.
        """
        course_export_dir = self._get_course_export_dir()
        is_draft = kwargs.pop('draft', False)
        xml_to_check = kwargs.pop('xml', None)
        xml_re_to_check = kwargs.pop('xml_re', None)
        xml_parse = kwargs.pop('xml_parse', None)

        block_path = self._get_block_type_path(course_export_dir, block_type, is_draft)
        block_contents = self._get_block_contents(block_path, block_id)
        if xml_to_check:
            self.assertIn(xml_to_check, block_contents)
        if xml_re_to_check:
            xml_re = re.compile(xml_re_to_check)
            self.assertIsNotNone(
                xml_re.search(block_contents),
                msg='Block ({}, {}) contents of:\n{}\n don\'t match regex of:\n{}'.format(
                    block_type, block_id, block_contents, xml_re_to_check
                )
            )
        if xml_parse:
            self._assert_parsed_xml(block_contents, xml_parse)

    def assertOLXMissing(self, block_type, block_id, **kwargs):
        """
        Assert that a particular block does not exist in a particular draft/published location.
        """
        course_export_dir = self._get_course_export_dir()
        is_draft = kwargs.pop('draft', False)
        block_path = self._get_block_type_path(course_export_dir, block_type, is_draft)
        block_file_path = os.path.join(block_path, self._get_block_filename(block_id))
        self.assertFalse(
            os.path.exists(block_file_path),
            msg='{} exists but should not!'.format(block_file_path)
        )

    def _make_deprecated_block_key(self, course_key, block_type, block_id):
        """
        Return a block key in the deprecated format.
        """
        return r'i4x://{ORG}/{COURSE}/{BLOCK_TYPE}/{BLOCK_ID}'.format(
            ORG=course_key.org,
            COURSE=course_key.course,
            BLOCK_TYPE=block_type,
            BLOCK_ID=block_id,
        )

    def _make_block_key(self, course_key, block_type, block_id):
        """
        Return a block key in the latest format.
        """
        return r'block-v1:{ORG}\+{COURSE}\+{RUN}\+type@{BLOCK_TYPE}\+block@{BLOCK_ID}'.format(
            ORG=course_key.org,
            COURSE=course_key.course,
            RUN=course_key.run,
            BLOCK_TYPE=block_type,
            BLOCK_ID=block_id,
        )

    def _make_xml_parse_regex(self, block_type, course_key, draft, **kwargs):
        """
        Construct a dictionary containing regular expressions that will
        be used to validate block XML.
        """
        parent_url_regex = None
        child_index_regex = None
        if draft:
            # Draft items are expected to have certain XML attributes.
            parent_type = kwargs.pop('parent_type', None)
            parent_id = kwargs.pop('parent_id', None)
            index_in_children_list = kwargs.pop('index_in_children_list', None)
            self.assertIsNotNone(
                parent_type,
                msg="Parent block type must be passed for draft {} item!".format(block_type)
            )
            self.assertIsNotNone(
                parent_id,
                msg="Parent block id must be passed for draft {} item!".format(block_type)
            )
            self.assertIsNotNone(
                index_in_children_list,
                msg="Index within {} must be passed for draft {} item!".format(parent_type, block_type)
            )
            parent_url_regex = '({DEPRECATED_PARENT_KEY}|{PARENT_KEY})'.format(
                DEPRECATED_PARENT_KEY=self._make_deprecated_block_key(course_key, parent_type, parent_id),
                PARENT_KEY=self._make_block_key(course_key, parent_type, parent_id),
            )
            child_index_regex = '{}'.format(index_in_children_list)

        # Form the checked attributes based on the block type.
        attrs = {}
        if block_type == 'html':
            filename = kwargs.pop('filename', None)
            attrs.update({'filename': filename})
        else:
            attrs.update({
                'parent_url': parent_url_regex,
                'index_in_children_list': child_index_regex
            })

        # If children exist, construct regular expressions to check them.
        child_id_regex = None
        child_type = None
        child_types_ids = kwargs.pop('child_ids', None)
        if child_types_ids:
            # Grab the type of the first child as the type of all the children.
            child_type = child_types_ids[0][0]
            # Construct regex out of all the child_ids that are included.
            child_id_regex = '|'.join([child[1] for child in child_types_ids])

        return {
            'tag': block_type,
            'attrs': attrs,
            'children': {
                'tag': child_type,
                'attrs': {'url_name' : child_id_regex},
            }
        }

    def _assertOLXBase(self, block_list, draft):  # pylint: disable=invalid-name
        """
        Check that all blocks in the list are draft blocks in the OLX format when the course is exported.
        """
        for block_data in block_list:
            block_params = self.course_db.get(block_data)
            self.assertIsNotNone(block_params)
            (block_type, block_id) = block_data
            xml_parse_regex = self._make_xml_parse_regex(block_type, self.course_key, draft=draft, **block_params)
            self.assertOLXContent(block_type, block_id, draft=draft, xml_parse=xml_parse_regex)
            self.assertOLXMissing(block_type, block_id, draft=(not draft))

    def assertOLXIsDraft(self, block_list):
        """
        Check that all blocks in the list are draft blocks in the OLX format when the course is exported.
        """
        self._assertOLXBase(block_list, draft=True)

    def assertOLXIsPublished(self, block_list):
        """
        Check that all blocks in the list are published blocks in the OLX format when the course is exported.
        """
        self._assertOLXBase(block_list, draft=False)

    def assertOLXIsDeleted(self, block_list):
        """
        Check that all blocks in the list are no longer in the OLX format when the course is exported.
        """
        for block_data in block_list:
            (block_type, block_id) = block_data
            self.assertOLXMissing(block_type, block_id, draft=True)
            self.assertOLXMissing(block_type, block_id, draft=False)


class UniversalTestProcedure(OLXFormatChecker, UniversalTestSetup):
    """
    Setup base class for draft/published/OLX tests.
    """

    EXPORTED_COURSE_BEFORE_DIR_NAME = 'exported_course_before'
    EXPORTED_COURSE_AFTER_DIR_NAME = 'exported_course_after_{}'

    def setUp(self):
        super(UniversalTestProcedure, self).setUp()
        self.export_dir = self.EXPORTED_COURSE_BEFORE_DIR_NAME
        self.root_export_dir = None
        self.contentstore = None
        self.store = None

    @contextmanager
    def _create_export_dir(self):
        """
        Create a temporary export dir - and clean it up when done.
        """
        try:
            export_dir = mkdtemp()
            yield export_dir
        finally:
            rmtree(export_dir, ignore_errors=True)

    @contextmanager
    def _setup_test(self, modulestore_builder, course_key):
        """
        Create the export dir, contentstore, and modulestore for a test.
        """
        with self._create_export_dir() as self.root_export_dir:
            # Construct the contentstore for storing the first import
            with MongoContentstoreBuilder().build() as self.contentstore:
                # Construct the modulestore for storing the first import (using the previously created contentstore)
                with modulestore_builder.build(contentstore=self.contentstore) as self.store:
                    # Create the course.
                    self.course = self._create_course(self.store, course_key)
                    yield

    def _export_if_not_already(self):
        """
        Check that the course has been exported. If not, export it.
        """
        exported_course_path = os.path.join(self.root_export_dir, self.export_dir)
        if not (os.path.exists(exported_course_path) and os.path.isdir(exported_course_path)):
            # Export the course.
            export_course_to_xml(
                self.store,
                self.contentstore,
                self.course_key,
                self.root_export_dir,
                self.export_dir,
            )

    def assertOLXContent(self, block_type, block_id, **kwargs):
        """
        Check that the course has been exported. If not, export it, then call the check.
        """
        self._export_if_not_already()
        super(UniversalTestProcedure, self).assertOLXContent(block_type, block_id, **kwargs)

    def assertOLXMissing(self, block_type, block_id, **kwargs):
        """
        Check that the course has been exported. If not, export it, then call the check.
        """
        self._export_if_not_already()
        super(UniversalTestProcedure, self).assertOLXMissing(block_type, block_id, **kwargs)

    def _make_new_export_dir_name(self):
        """
        Make a unique name for the new export dir.
        """
        return self.EXPORTED_COURSE_AFTER_DIR_NAME.format(unicode(uuid.uuid4())[:8])

    def publish(self, block_type, block_id):
        """
        Get an item, publish it, and shift to a new course export dir.
        """
        # Get the specified test item from the draft branch.
        with self.store.branch_setting(ModuleStoreEnum.Branch.draft_preferred):
            test_item = self.store.get_item(self.course_key.make_usage_key(block_type=block_type, block_id=block_id))
        # Publish the draft item to the published branch.
        self.store.publish(test_item.location, self.user_id)
        # Since the elemental operation is now complete, shift to the post-operation export directory name.
        self.export_dir = self._make_new_export_dir_name()

    def unpublish(self, block_type, block_id):
        """
        Get an item, unpublish it, and shift to a new course export dir.
        """
        # Get the specified test item from the published branch.
        with self.store.branch_setting(ModuleStoreEnum.Branch.published_only):
            test_item = self.store.get_item(self.course_key.make_usage_key(block_type=block_type, block_id=block_id))
        # Unpublish the draft item from the published branch.
        self.store.unpublish(test_item.location, self.user_id)
        # Since the elemental operation is now complete, shift to the post-operation export directory name.
        self.export_dir = self._make_new_export_dir_name()


@ddt.ddt
class ElementalPublishingTests(UniversalTestProcedure):
    """
    Tests for the publish() operation.
    """
    @ddt.data(*MODULESTORE_SETUPS)
    def test_autopublished_chapters_sequentials(self, modulestore_builder):
        with self._setup_test(modulestore_builder, self.course_key):
            # When a course is created out of chapters/sequentials/verticals/units
            # as this course is, the chapters/sequentials are auto-published
            # and the verticals/units are not.
            # Ensure that this is indeed the case by verifying the OLX.
            block_list_autopublished = (
                ('chapter', 'chapter00'),
                ('chapter', 'chapter01'),
                ('sequential', 'sequential00'),
                ('sequential', 'sequential01'),
                ('sequential', 'sequential02'),
                ('sequential', 'sequential03'),
            )
            block_list_draft = self.all_verticals + self.all_units
            self.assertOLXIsPublished(block_list_autopublished)
            self.assertOLXIsDraft(block_list_draft)

    @ddt.data(DRAFT_MODULESTORE_SETUP, MongoModulestoreBuilder())
    def test_publish_old_mongo_unit(self, modulestore_builder):
        with self._setup_test(modulestore_builder, self.course_key):

            # In old Mongo, you can successfully publish an item whose parent
            # isn't published.
            self.publish('html', 'unit00')

    @ddt.data(SPLIT_MODULESTORE_SETUP)
    def test_publish_split_unit(self, modulestore_builder):
        with self._setup_test(modulestore_builder, self.course_key):

            # In Split, you cannot publish an item whose parents are unpublished.
            # Split will raise an exception when the item's parent(s) aren't found
            # in the published branch.
            with self.assertRaises(ItemNotFoundError):
                self.publish('html', 'unit00')

    @ddt.data(*MODULESTORE_SETUPS)
    def test_publish_multiple_verticals(self, modulestore_builder):
        with self._setup_test(modulestore_builder, self.course_key):

            block_list_publish = (
                ('vertical', 'vertical03'),
                ('vertical', 'vertical04'),
                ('html', 'unit06'),
                ('html', 'unit07'),
                ('html', 'unit08'),
                ('html', 'unit09'),
            )
            block_list_untouched = (
                ('vertical', 'vertical00'),
                ('vertical', 'vertical01'),
                ('vertical', 'vertical02'),
                ('vertical', 'vertical05'),
                ('vertical', 'vertical06'),
                ('vertical', 'vertical07'),
                ('html', 'unit00'),
                ('html', 'unit01'),
                ('html', 'unit02'),
                ('html', 'unit03'),
                ('html', 'unit04'),
                ('html', 'unit05'),
                ('html', 'unit10'),
                ('html', 'unit11'),
                ('html', 'unit12'),
                ('html', 'unit13'),
                ('html', 'unit14'),
                ('html', 'unit15'),
            )

            # Ensure that both groups of verticals and children are drafts in the exported OLX.
            self.assertOLXIsDraft(block_list_publish)
            self.assertOLXIsDraft(block_list_untouched)

            # Publish both vertical03 and vertical 04.
            self.publish('vertical', 'vertical03')
            self.publish('vertical', 'vertical04')

            # Ensure that the published verticals and children are indeed published in the exported OLX.
            self.assertOLXIsPublished(block_list_publish)
            # Ensure that the untouched vertical and children are still untouched.
            self.assertOLXIsDraft(block_list_untouched)

    @ddt.data(*MODULESTORE_SETUPS)
    def test_publish_single_sequential(self, modulestore_builder):
        """
        Sequentials are auto-published. But publishing them explictly publishes their children,
        changing the OLX of each sequential - the vertical children are in the sequential post-publish.
        """
        with self._setup_test(modulestore_builder, self.course_key):

            block_list_autopublished = (
                ('sequential', 'sequential00'),
            )
            block_list = (
                ('vertical', 'vertical00'),
                ('vertical', 'vertical01'),
                ('html', 'unit00'),
                ('html', 'unit01'),
                ('html', 'unit02'),
                ('html', 'unit03'),
            )
            # Ensure that the autopublished sequential exists as such in the exported OLX.
            self.assertOLXIsPublished(block_list_autopublished)
            # Ensure that the verticals and their children are drafts in the exported OLX.
            self.assertOLXIsDraft(block_list)
            # Publish the sequential block.
            self.publish('sequential', 'sequential00')
            # Ensure that the sequential is still published in the exported OLX.
            self.assertOLXIsPublished(block_list_autopublished)
            # Ensure that the verticals and their children are published in the exported OLX.
            self.assertOLXIsPublished(block_list)

    @ddt.data(*MODULESTORE_SETUPS)
    def test_publish_single_chapter(self, modulestore_builder):
        """
        Chapters are auto-published.
        """
        with self._setup_test(modulestore_builder, self.course_key):

            block_list_autopublished = (
                ('chapter', 'chapter00'),
            )
            block_list_published = (
                ('vertical', 'vertical00'),
                ('vertical', 'vertical01'),
                ('vertical', 'vertical02'),
                ('vertical', 'vertical03'),
                ('html', 'unit00'),
                ('html', 'unit01'),
                ('html', 'unit02'),
                ('html', 'unit03'),
                ('html', 'unit04'),
                ('html', 'unit05'),
                ('html', 'unit06'),
                ('html', 'unit07'),
            )
            block_list_untouched = (
                ('vertical', 'vertical04'),
                ('vertical', 'vertical05'),
                ('vertical', 'vertical06'),
                ('vertical', 'vertical07'),
                ('html', 'unit08'),
                ('html', 'unit09'),
                ('html', 'unit10'),
                ('html', 'unit11'),
                ('html', 'unit12'),
                ('html', 'unit13'),
                ('html', 'unit14'),
                ('html', 'unit15'),
            )
            # Ensure that the autopublished chapter exists as such in the exported OLX.
            self.assertOLXIsPublished(block_list_autopublished)
            # Ensure that the verticals and their children are drafts in the exported OLX.
            self.assertOLXIsDraft(block_list_published)
            self.assertOLXIsDraft(block_list_untouched)
            # Publish the chapter block.
            self.publish('chapter', 'chapter00')
            # Ensure that the chapter is still published in the exported OLX.
            self.assertOLXIsPublished(block_list_autopublished)
            # Ensure that the vertical and its children are published in the exported OLX.
            self.assertOLXIsPublished(block_list_published)
            # Ensure that the other vertical and children are not published.
            self.assertOLXIsDraft(block_list_untouched)


@ddt.ddt
class ElementalUnpublishingTests(UniversalTestProcedure):
    """
    Tests for the unpublish() operation.
    """
    @ddt.data(*MODULESTORE_SETUPS)
    def test_unpublish_draft_vertical(self, modulestore_builder):
        with self._setup_test(modulestore_builder, self.course_key):

            block_list_to_unpublish = (
                ('vertical', 'vertical02'),
            )
            # The vertical is a draft.
            self.assertOLXIsDraft(block_list_to_unpublish)
            # Since there's no published version, attempting an unpublish throws an exception.
            with self.assertRaises(ItemNotFoundError):
                self.unpublish('vertical', 'vertical02')

    @ddt.data(*MODULESTORE_SETUPS)
    def test_unpublish_published_vertical(self, modulestore_builder):
        with self._setup_test(modulestore_builder, self.course_key):

            block_list_to_unpublish = (
                ('vertical', 'vertical02'),
            )
            block_list_children_of_unpublished = (
                ('html', 'unit04'),
                ('html', 'unit05'),
            )
            block_list_untouched = (
                ('vertical', 'vertical04'),
                ('vertical', 'vertical05'),
                ('vertical', 'vertical06'),
                ('vertical', 'vertical07'),
                ('html', 'unit08'),
                ('html', 'unit09'),
                ('html', 'unit10'),
                ('html', 'unit11'),
                ('html', 'unit12'),
                ('html', 'unit13'),
                ('html', 'unit14'),
                ('html', 'unit15'),
            )
            # At first, no vertical or unit is published.
            self.assertOLXIsDraft(block_list_to_unpublish)
            self.assertOLXIsDraft(block_list_children_of_unpublished)
            self.assertOLXIsDraft(block_list_untouched)
            # Then publish a vertical.
            self.publish('vertical', 'vertical02')
            # The published vertical and its children will be published.
            self.assertOLXIsPublished(block_list_to_unpublish)
            self.assertOLXIsPublished(block_list_children_of_unpublished)
            self.assertOLXIsDraft(block_list_untouched)
            # Now, unpublish the same vertical.
            self.unpublish('vertical', 'vertical02')
            # The unpublished vertical and its children will now be a draft.
            self.assertOLXIsDraft(block_list_to_unpublish)
            self.assertOLXIsDraft(block_list_children_of_unpublished)
            self.assertOLXIsDraft(block_list_untouched)

    @ddt.data(DRAFT_MODULESTORE_SETUP, MongoModulestoreBuilder())
    def test_unpublish_old_mongo_draft_sequential(self, modulestore_builder):
        with self._setup_test(modulestore_builder, self.course_key):

            # In old Mongo, you cannot successfully unpublish an autopublished sequential.
            # An exception is thrown.
            with self.assertRaises(InvalidVersionError):
                self.unpublish('sequential', 'sequential03')

    @ddt.data(SPLIT_MODULESTORE_SETUP)
    def test_unpublish_split_draft_sequential(self, modulestore_builder):
        with self._setup_test(modulestore_builder, self.course_key):

            # In Split, the sequential is deleted.
            # The sequential's children are orphaned - but they stay in
            # the same draft state they were before.
            block_list_to_unpublish = (
                ('sequential', 'sequential03'),
            )
            block_list_children_of_unpublished = (
                ('vertical', 'vertical06'),
                ('vertical', 'vertical07'),
                ('html', 'unit12'),
                ('html', 'unit13'),
                ('html', 'unit14'),
                ('html', 'unit15'),
            )
            # The autopublished sequential is published - its children are draft.
            self.assertOLXIsPublished(block_list_to_unpublish)
            self.assertOLXIsDraft(block_list_children_of_unpublished)
            # Unpublish the sequential.
            self.unpublish('sequential', 'sequential03')
            # Since the sequential was autopublished, a draft version of the sequential never existed.
            # So unpublishing the sequential doesn't make it a draft - it deletes it!
            self.assertOLXIsDeleted(block_list_to_unpublish)
            # Its children are orphaned and remain as drafts.
            self.assertOLXIsDraft(block_list_children_of_unpublished)

