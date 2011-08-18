from datetime import datetime
from django.utils import unittest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError

from flag.models import FlaggedContent, FlagInstance
from flag.tests.models import ModelWithoutAuthor, ModelWithAuthor
from flag import settings as flag_settings
from flag.exceptions import *
from flag.signals import content_flagged

class BaseTestCase(unittest.TestCase):
    """
    Base test class to save old flag settings, remove them, and add some
    helper to easily create flags
    """

    def setUp(self):
        """
        Save old settings and set them to default
        """
        super(BaseTestCase, self).setUp()
        self.old_settings = dict((key, getattr(flag_settings, key)) for key in flag_settings.__all__)

    def tearDown(self):
        """
        Restore old settings
        """
        for key, value in self.old_settings.items():
            setattr(flag_settings, key, value)
        super(BaseTestCase, self).tearDown()

    def assertNotRaises(self, callableObj, *args, **kwargs):
        """
        Check that an exception is not raised
        """
        try:
            callableObj(*args, **kwargs)
        except Exception, e:
            raise self.failureException("%s raised" % e.__class__.__name__)

    def _add_flagged_content(self, obj, creator=None):
        """
        Create a flag for the given object
        """
        params = dict(
            content_type = ContentType.objects.get_for_model(obj),
            object_id = obj.id,
        )
        if creator:
            params['creator'] = creator

        flagged_content = FlaggedContent.objects.create(**params)
        return flagged_content

    def _delete_flagged_contents(self):
        """
        Remove all flagged contents
        """
        FlaggedContent.objects.all().delete()

    def _add_flag(self, flagged_content, comment=None):
        """
        Add a flag to the given flagged_content
        """
        params = dict(
            user = self.user,
        )
        if comment:
            params['comment'] = comment
        flag = flagged_content.flaginstance_set.create(**params)
        return flag

    def _delete_flags(self):
        """
        Remove all flags
        """
        FlagInstance.objects.all().delete()


class FlagModelsTestCase(BaseTestCase):

    def setUp(self):
        """
        Add a user which will make the flags, and two flaggable objects
        """
        super(FlagModelsTestCase, self).setUp()

        # flagger
        self.user = User.objects.create(username='test', email='test@example.com', password='test')
        # author of objects
        self.author = User.objects.create(username='author', email='author@exanple.com', password='author')
        # model without author
        self.model_without_author = ModelWithoutAuthor.objects.create(name='foo')
        # model with author
        self.model_with_author = ModelWithAuthor.objects.create(name='bar', author=self.author)

    def tearDown(self):
        """
        Drop all objects
        """
        self._delete_flags()
        self._delete_flagged_contents()
        ModelWithoutAuthor.objects.all().delete()
        ModelWithAuthor.objects.all().delete()
        User.objects.all().delete()

        super(FlagModelsTestCase, self).tearDown()


    def test_model_can_be_flagged(self):
        """
        Test if a model can be flagged (via the MODELS settings)
        """
        # default setting : all models can be flagged
        flag_settings.MODELS = None
        self.assertTrue(
            FlaggedContent.objects.model_can_be_flagged(self.model_without_author))
        self.assertNotRaises(
            FlaggedContent.objects.assert_model_can_be_flagged, self.model_without_author)
        self.assertTrue(
            FlaggedContent.objects.model_can_be_flagged(self.model_with_author))
        self.assertNotRaises(
            FlaggedContent.objects.assert_model_can_be_flagged, self.model_with_author)

        # only one model can be flagged
        flag_settings.MODELS = ('tests.modelwithauthor',)
        self.assertFalse(
            FlaggedContent.objects.model_can_be_flagged(self.model_without_author))
        self.assertRaises(ModelCannotBeFlaggedException,
            FlaggedContent.objects.assert_model_can_be_flagged, self.model_without_author)
        self.assertTrue(
            FlaggedContent.objects.model_can_be_flagged(self.model_with_author))
        self.assertNotRaises(
            FlaggedContent.objects.assert_model_can_be_flagged, self.model_with_author)

    def test_add_forbidden_flagged_content(self):
        """
        Try to add a FlaggedContent object regarding the MODELS settings
        """

        # default settings : all models can be flagged
        flag_settings.MODELS = None
        self.assertNotRaises(
            self._add_flagged_content, self.model_without_author)
        self.assertNotRaises(
            self._add_flagged_content, self.model_with_author)

        # only one model can be flagged
        self._delete_flagged_contents()
        flag_settings.MODELS = ('tests.modelwithauthor',)
        self.assertRaises(ModelCannotBeFlaggedException,
            self._add_flagged_content, self.model_without_author)
        self.assertNotRaises(
            self._add_flagged_content, self.model_with_author)

    def test_flagged_content_unicity(self):
        """
        Test that we cannot add more than one FlaggedContent for the same object
        """
        self.assertNotRaises(
            self._add_flagged_content, self.model_without_author)
        self.assertNotRaises(
            self._add_flagged_content, self.model_with_author)
        self.assertRaises(IntegrityError,
            self._add_flagged_content, self.model_without_author)
        self.assertRaises(IntegrityError,
            self._add_flagged_content, self.model_with_author)


    def test_object_can_be_flagged(self):
        """
        Test if an object can be flagged (via the LIMIT_FOR_OBJECT settings)
        """
        # create the FlaggedContent object, with 0 tags
        flagged_content = self._add_flagged_content(self.model_without_author)

        # test with count=1
        flagged_content.count = 1

        flag_settings.LIMIT_FOR_OBJECT = 0
        self.assertTrue(flagged_content.can_be_flagged())
        self.assertNotRaises(flagged_content.assert_can_be_flagged)

        flag_settings.LIMIT_FOR_OBJECT = 1
        self.assertFalse(flagged_content.can_be_flagged())
        self.assertRaises(ContentFlaggedEnoughException,
            flagged_content.assert_can_be_flagged)

        flag_settings.LIMIT_FOR_OBJECT = 2
        self.assertTrue(flagged_content.can_be_flagged())
        self.assertNotRaises(flagged_content.assert_can_be_flagged)

        # test with count=10
        flagged_content.count = 10

        flag_settings.LIMIT_FOR_OBJECT = 0
        self.assertTrue(flagged_content.can_be_flagged())
        self.assertNotRaises(flagged_content.assert_can_be_flagged)

        flag_settings.LIMIT_FOR_OBJECT = 1
        self.assertFalse(flagged_content.can_be_flagged())
        self.assertRaises(ContentFlaggedEnoughException,
            flagged_content.assert_can_be_flagged)

        flag_settings.LIMIT_FOR_OBJECT = 10
        self.assertFalse(flagged_content.can_be_flagged())
        self.assertRaises(ContentFlaggedEnoughException,
            flagged_content.assert_can_be_flagged)

        flag_settings.LIMIT_FOR_OBJECT = 20
        self.assertTrue(flagged_content.can_be_flagged())
        self.assertNotRaises(flagged_content.assert_can_be_flagged)

    def test_add_too_much_flags(self):
        """
        Try to add flags to objects regarding the LIMIT_FOR_OBJECT settings)
        """
        def add():
            return FlagInstance.objects.add(self.user, self.model_without_author, comment='comment')

        # test without limit
        for i in range(0, 5):
            self.assertNotRaises(add)

        # test with limit=10
        flag_settings.LIMIT_FOR_OBJECT=10
        for i in range(0, 5):
            self.assertNotRaises(add)

        # fail for the 11th
        self.assertRaises(ContentFlaggedEnoughException, add)

    def test_object_can_be_flagged_by_user(self):
        """
        Test if an object can be flagged by a user (via the LIMIT_SAME_OBJECT_FOR_USER settings)
        """
        # create the FlaggedContent object
        flagged_content = self._add_flagged_content(self.model_without_author)

        # test with only one flag
        self._add_flag(flagged_content, 'comment')

        flag_settings.LIMIT_SAME_OBJECT_FOR_USER = 0
        self.assertTrue(flagged_content.can_be_flagged_by_user(self.user))
        self.assertNotRaises(flagged_content.assert_can_be_flagged_by_user, self.user)

        flag_settings.LIMIT_SAME_OBJECT_FOR_USER = 1
        self.assertFalse(flagged_content.can_be_flagged_by_user(self.user))
        self.assertRaises(ContentAlreadyFlaggedByUserException,
            flagged_content.assert_can_be_flagged_by_user, self.user)

        flag_settings.LIMIT_SAME_OBJECT_FOR_USER = 2
        self.assertTrue(flagged_content.can_be_flagged_by_user(self.user))
        self.assertNotRaises(flagged_content.assert_can_be_flagged_by_user, self.user)

        # test with 10 flags
        flag_settings.LIMIT_SAME_OBJECT_FOR_USER = 0
        for i in range(0, 9):
            self._add_flag(flagged_content, 'comment')

        self.assertTrue(flagged_content.can_be_flagged_by_user(self.user))
        self.assertNotRaises(flagged_content.assert_can_be_flagged_by_user, self.user)

        flag_settings.LIMIT_SAME_OBJECT_FOR_USER = 1
        self.assertFalse(flagged_content.can_be_flagged_by_user(self.user))
        self.assertRaises(ContentAlreadyFlaggedByUserException,
            flagged_content.assert_can_be_flagged_by_user, self.user)

        flag_settings.LIMIT_SAME_OBJECT_FOR_USER = 10
        self.assertFalse(flagged_content.can_be_flagged_by_user(self.user))
        self.assertRaises(ContentAlreadyFlaggedByUserException,
            flagged_content.assert_can_be_flagged_by_user, self.user)

        flag_settings.LIMIT_SAME_OBJECT_FOR_USER = 20
        self.assertTrue(flagged_content.can_be_flagged_by_user(self.user))
        self.assertNotRaises(flagged_content.assert_can_be_flagged_by_user, self.user)

    def test_add_too_much_flags_for_user(self):
        """
        Try to add flags to objects regarding the LIMIT_SAME_OBJECT_FOR_USER settings)
        """
        def add(user):
            return FlagInstance.objects.add(user, self.model_without_author, comment='comment')

        user2 = User.objects.create(username='test2', email='test2@example.com', password='test2')

        # test without limit
        for i in range(0, 5):
            self.assertNotRaises(add, self.user)

        # test with limit=10
        flag_settings.LIMIT_SAME_OBJECT_FOR_USER=10
        for i in range(0, 5):
            self.assertNotRaises(add, self.user)

        # fail for the 11th
        self.assertRaises(ContentAlreadyFlaggedByUserException, add, self.user)

        # do not fail for another user
        for i in range(0, 10):
            self.assertNotRaises(add, user2)
        #... until the max
        self.assertRaises(ContentAlreadyFlaggedByUserException, add, user2)

    def test_comments(self):
        """
        Test adding a flag with or without a comment, regarding the ALLOW_COMMENTS settings
        """
        def add(with_comment):
            params = dict()
            if with_comment:
                params['comment'] = 'comment'
            return FlagInstance.objects.add(self.user, self.model_without_author, **params)

        # allow
        flag_settings.ALLOW_COMMENTS = True
        self.assertNotRaises(add, True)
        self.assertRaises(FlagCommentException, add, False)

        # disallow
        flag_settings.ALLOW_COMMENTS = False
        self.assertRaises(FlagCommentException, add, True)
        self.assertNotRaises(add, False)

    def test_count_flags_for_object(self):
        """
        Test the total flags count for an object by adding flags
        """
        def add():
            return FlagInstance.objects.add(self.user, self.model_without_author, comment='comment')

        # test by simply adding flags
        self.assertEqual(add().flagged_content.count, 1)
        self.assertEqual(add().flagged_content.count, 2)

        # update a flag : the count shouldn't change
        flag = FlagInstance.objects.all()[0]
        previous_count = flag.flagged_content.count
        flag.when_added = datetime.now()
        flag.save()
        self.assertEqual(flag.flagged_content.count, previous_count)


    def test_count_flags_by_user(self):
        """
        Test if the count_flag_by_users is correct
        """
        flagged_content = self._add_flagged_content(self.model_without_author)

        self.assertEqual(flagged_content.count_flags_by_user(self.user), 0)
        self._add_flag(flagged_content, 'comment')
        self.assertEqual(flagged_content.count_flags_by_user(self.user), 1)
        for i in range(0, 9):
            self._add_flag(flagged_content, 'comment')
        self.assertEqual(flagged_content.count_flags_by_user(self.user), 10)

    def test_signal(self):
        """
        Test if the signal is correctly send
        """
        def receive_signal(sender, signal, flagged_content, flagged_instance):
            self.signal_received = dict(
                flagged_content = flagged_content,
                flagged_instance = flagged_instance
            )

        def clear_received_signal():
            if hasattr(self, 'signal_received'):
                delattr(self, 'signal_received')

        def add():
            return FlagInstance.objects.add(self.user, self.model_without_author, comment='comment')

        # connect to the signal
        self.assertNotRaises(content_flagged.connect, receive_signal)

        # add a flag => send a signal
        flag = add()
        self.assertEqual(self.signal_received['flagged_instance'], flag)

        clear_received_signal()

        # update the flag => do not send signal
        flag.when_added = datetime.now()
        flag.save()
        self.assertRaises(AttributeError, getattr, self, 'signal_received')

        clear_received_signal()


