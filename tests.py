# -*- coding: utf-8 -*-

import types
import unittest
from testalchemy import Sample, Restorable, DBHistory, sample_property
import sqlalchemy.exc
from sqlalchemy import (
        MetaData, Table, Column, String, Integer, ForeignKey,
        create_engine, UniqueConstraint)
from sqlalchemy.orm import relation, sessionmaker
from sqlalchemy.ext.declarative import declarative_base


metadata = MetaData()
Model = declarative_base(metadata=metadata, name='Model')


class User(Model):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, default='')
    roles = relation('Role', passive_deletes='all')


class Category(Model):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    roles = relation('Role', secondary='roles_category', passive_deletes='all')


class Role(Model):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey(User.id, ondelete='CASCADE'), nullable=False)
    user = relation(User)
    categories = relation(Category, secondary='roles_category', passive_deletes='all')
    smi_id = Column(ForeignKey('smi.id', ondelete='CASCADE'), nullable=False)
    smi = relation('Smi')


class Smi(Model):
    __tablename__ = 'smi'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    roles = relation(Role, passive_deletes='all')


roles_category = Table('roles_category', metadata, 
    Column('role_id', ForeignKey(Role.id, ondelete='CASCADE'), nullable=False),
    Column('category_id', ForeignKey(Category.id, ondelete='CASCADE'), nullable=False),
    UniqueConstraint('role_id', 'category_id')
)

EMPTY = object()


class Test(unittest.TestCase):

    def setUp(self):
        engine = create_engine('sqlite:///:memory:', echo=False)
        metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.session = self.Session()

    def tearDown(self):
        self.session.close()

    def assert_attr(self, obj, attr_name, type_of=None, value=EMPTY):
        self.assertTrue(hasattr(obj, attr_name),
                        '%r has no attribute %s' % (obj, attr_name))
        attr = getattr(obj, attr_name)
        if type_of is not None:
            self.assertTrue(isinstance(attr, type_of),
                             'Attribute %r is not %r type' % (attr, type_of))
        if value is not EMPTY:
            self.assertEqual(attr, value)

    def test_restorable_and_normal_behavior(self):
        session = self.session
        with Restorable(session):
            smi = Smi(name='newspaper')
            cat1 = Category(name='cat1')
            cat2 = Category(name='cat2')
            user = User(name='john')
            role = Role(user=user, smi=smi, categories=[cat1, cat2])
            session.add_all([smi, cat1, cat2, user, role])
            session.commit()
        self.assertEqual(self.session.query(User).all(), [])
        self.assertEqual(self.session.query(Category).all(), [])
        self.assertEqual(self.session.query(Role).all(), [])
        self.assertEqual(self.session.query(Smi).all(), [])

    def test_restorable_and_exceptional_behavior(self):
        session = self.session
        def exceptional_behavior():
            with Restorable(session):
                smi = Smi(name='newspaper')
                cat1 = Category(name='cat1')
                cat2 = Category(name='cat2')
                user = User(name='john')
                role = Role(user=user, smi=smi, categories=[cat1, cat2])
                session.add_all([smi, cat1, cat2, user, role])
                session.commit()
                raise Exception('unwanted')
        self.assertRaises(Exception, exceptional_behavior)
        self.assertEqual(session.query(User).all(), [])
        self.assertEqual(session.query(Category).all(), [])
        self.assertEqual(session.query(Role).all(), [])
        self.assertEqual(session.query(Smi).all(), [])

    def test_restorable_and_dirty_session(self):
        session = self.session
        def dirty_session():
            with Restorable(session):
                smi = Smi(name='newspaper')
                cat1 = Category(name='cat1')
                cat2 = Category(name='cat2')
                user = User(name='john')
                role = Role(user=user, smi=smi, categories=[cat1, cat1])
                session.add_all([smi, cat1, cat2, user, role])
                session.commit()
        self.assertRaises(sqlalchemy.exc.IntegrityError, dirty_session)
        self.assertEqual(session.query(User).all(), [])
        self.assertEqual(session.query(Category).all(), [])
        self.assertEqual(session.query(Role).all(), [])
        self.assertEqual(session.query(Smi).all(), [])

    def test_models_history_init(self):
        with DBHistory(self.session) as history:
            self.assertEqual(history.created, set())
            self.assertEqual(history.updated, set())
            self.assertEqual(history.deleted, set())
            self.assertEqual(history.created_idents, {})
            self.assertEqual(history.updated_idents, {})
            self.assertEqual(history.deleted_idents, {})
            self.assertEqual(history.last_created(User), set())
            self.assertEqual(history.last_updated(User), set())
            self.assertEqual(history.last_deleted(User), set())
            self.assertRaises(AssertionError, history.assert_created, User)
            self.assertRaises(AssertionError, history.assert_updated, User)
            self.assertRaises(AssertionError, history.assert_deleted, User)

    def test_models_history_created(self):
        session = self.session
        with DBHistory(session) as history:
            user = User(name='test')
            session.add(user)
            session.commit()
            self.assertEqual(history.created, set([user]))
            self.assertEqual(history.updated, set())
            self.assertEqual(history.deleted, set())
            self.assertEqual(history.created_idents, {User: set([(1,)])})
            self.assertEqual(history.updated_idents, {})
            self.assertEqual(history.deleted_idents, {})
            self.assertEqual(history.last_created(User), set([user]))
            self.assertEqual(history.last_updated(User), set())
            self.assertEqual(history.last_deleted(User), set())
            self.assertEqual(history.assert_created(User), set([user]))
            self.assertEqual(history.assert_created(User, user.id), user)
            self.assertEqual(history.assert_created_one(User), user)
            self.assertRaises(AssertionError, history.assert_updated, User)
            self.assertRaises(AssertionError, history.assert_updated_one, User)
            self.assertRaises(AssertionError, history.assert_deleted, User)
            self.assertRaises(AssertionError, history.assert_deleted_one, User)

    def test_models_history_updated(self):
        session = self.session
        user = User(name='test')
        session.add(user)
        session.commit()
        session.expire_all()
        with DBHistory(session) as history:
            user = session.query(User).get(user.id)
            user.name = 'test 1'
            session.commit()
            self.assertEqual(history.created, set())
            self.assertEqual(history.updated, set([user]))
            self.assertEqual(history.deleted, set())
            self.assertEqual(history.created_idents, {})
            self.assertEqual(history.updated_idents, {User: set([(1,)])})
            self.assertEqual(history.deleted_idents, {})
            self.assertEqual(history.last_created(User), set())
            self.assertEqual(history.last_updated(User), set([user]))
            self.assertEqual(history.last_deleted(User), set())
            self.assertRaises(AssertionError, history.assert_created, User)
            self.assertRaises(AssertionError, history.assert_created_one, User)
            self.assertEqual(history.assert_updated(User), set([user]))
            self.assertEqual(history.assert_updated(User, user.id), user)
            self.assertEqual(history.assert_updated_one(User), user)
            self.assertRaises(AssertionError, history.assert_deleted, User)
            self.assertRaises(AssertionError, history.assert_deleted_one, User)

    def test_models_history_deleted(self):
        session = self.session
        user = User(name='test')
        session.add(user)
        session.commit()
        session.expire_all()
        with DBHistory(session) as history:
            user = session.query(User).get(user.id)
            session.delete(user)
            session.commit()
            self.assertEqual(history.created, set())
            self.assertEqual(history.updated, set())
            self.assertEqual(history.deleted, set([user]))
            self.assertEqual(history.created_idents, {})
            self.assertEqual(history.updated_idents, {})
            self.assertEqual(history.deleted_idents, {User: set([(1,)])})
            self.assertEqual(history.last_created(User), set())
            self.assertEqual(history.last_updated(User), set())
            self.assertEqual(history.last_deleted(User), set([user]))
            self.assertRaises(AssertionError, history.assert_created, User)
            self.assertRaises(AssertionError, history.assert_created_one, User)
            self.assertRaises(AssertionError, history.assert_updated, User)
            self.assertRaises(AssertionError, history.assert_updated_one, User)
            self.assertEqual(history.assert_deleted(User), set([user]))
            self.assertEqual(history.assert_deleted(User, user.id), user)
            self.assertEqual(history.assert_deleted_one(User), user)

    def test_sample_properties(self):
        class TestSample(Sample):
            def method(self):
                pass
            def _method(self):
                pass
        self.assert_attr(TestSample, 'method', sample_property)
        self.assert_attr(TestSample, '_method', types.MethodType)
        self.assert_attr(TestSample, '_decorated_methods',
                         value={'method': TestSample.method.method})

    def test_sample_properties_with_inheritance(self):
        class BaseTestSample(Sample):
            def method(self):
                pass
            def _method(self):
                pass
        class TestSample(BaseTestSample):
            def method1(self):
                pass
            def _method1(self):
                pass
        self.assert_attr(TestSample, 'method', sample_property)
        self.assert_attr(TestSample, 'method1', sample_property)
        self.assert_attr(TestSample, '_method', types.MethodType)
        self.assert_attr(TestSample, '_method1', types.MethodType)
        self.assert_attr(TestSample, '_decorated_methods',
                         value={'method': TestSample.method.method,
                                'method1': TestSample.method1.method})

    def test_sample_creation(self):
        class DataSample(Sample):
            def john(self):
                return User(name='john')
            def cat1(self):
                return Category(name='cat1')
            def cat2(self):
                return Category(name='cat2')
            def newspaper_editor(self):
                return Role(user=self.john, smi=self.newspaper,
                            categories=[self.cat1, self.cat2])
            def newspaper(self):
                return Smi(name='newspaper')
        sample = DataSample(self.session)
        sample.create_all()
        self.assertEqual(self.session.query(User).all(), [sample.john])
        self.assertEqual(set(self.session.query(Category).all()),
                         set([sample.cat1, sample.cat2]))
        self.assertEqual(self.session.query(Role).all(),
                         [sample.newspaper_editor])
        self.assertEqual(self.session.query(Smi).all(),
                         [sample.newspaper])

    def test_sample_creation_with_mixins(self):
        class SampleCat(Sample):
            def cat1(self):
                return Category(name='cat1')
            def cat2(self):
                return Category(name='cat2')
            def cat3(self):
                return Category(name='cat3')
        class Mixin(object):
            def john(self):
                return User(name='john')
        class DataSample(SampleCat, Mixin):
            def newspaper_editor(self):
                return Role(user=self.john, smi=self.newspaper,
                            categories=[self.cat1, self.cat2])
            def newspaper(self):
                return Smi(name='newspaper')
        sample = DataSample(self.session)
        sample.create_all()
        self.assertEqual(self.session.query(User).all(), [sample.john])
        self.assertEqual(set(self.session.query(Category).all()),
                         set([sample.cat1, sample.cat2, sample.cat3]))
        self.assertEqual(self.session.query(Role).all(),
                         [sample.newspaper_editor])
        self.assertEqual(self.session.query(Smi).all(),
                         [sample.newspaper])

    def test_sample_with_mixin(self):
        class Mixin1(object):
            def method(self):
                pass
            def _method(self):
                pass
        class Mixin2(object):
            def method1(self):
                pass
            def _method1(self):
                pass
        class TestSample(Sample, Mixin1, Mixin2):
            def method2(self):
                pass
            def _method2(self):
                pass
        self.assert_attr(TestSample, 'method', sample_property)
        self.assert_attr(TestSample, 'method1', sample_property)
        self.assert_attr(TestSample, 'method2', sample_property)
        self.assert_attr(TestSample, '_method', types.MethodType)
        self.assert_attr(TestSample, '_method1', types.MethodType)
        self.assert_attr(TestSample, '_method2', types.MethodType)
        self.assert_attr(TestSample, '_decorated_methods',
                         value={'method': TestSample.method.method,
                                'method1': TestSample.method1.method,
                                'method2': TestSample.method2.method})

    def test_sample_with_oldstyle_mixin(self):
        class Mixin1(object):
            def method(self):
                pass
            def _method(self):
                pass
        class Mixin2:
            def method1(self):
                pass
            def _method1(self):
                pass
        class TestSample(Sample, Mixin1, Mixin2):
            def method2(self):
                pass
            def _method2(self):
                pass
        self.assert_attr(TestSample, 'method', sample_property)
        self.assert_attr(TestSample, 'method1', sample_property)
        self.assert_attr(TestSample, 'method2', sample_property)
        self.assert_attr(TestSample, '_method', types.MethodType)
        self.assert_attr(TestSample, '_method1', types.MethodType)
        self.assert_attr(TestSample, '_method2', types.MethodType)
        self.assert_attr(TestSample, '_decorated_methods',
                         value={'method': TestSample.method.method,
                                'method1': TestSample.method1.method,
                                'method2': TestSample.method2.method})

    def test_class_attr_assigning(self):
        class LibSample(Sample):
            def method(self):
                pass
        class TestSample(Sample):
            method = LibSample.method
        self.assert_attr(LibSample, 'method', sample_property)
        self.assert_attr(LibSample, '_decorated_methods',
                         value={'method': LibSample.method.method})
        self.assert_attr(TestSample, 'method', sample_property)
        self.assert_attr(TestSample, '_decorated_methods',
                         value={'method': TestSample.method.method})

    def test_assigning_class_attr_with_new_name(self):
        class LibSample(Sample):
            def method2(self):
                pass
        class TestSample(Sample):
            method = LibSample.method2
        self.assert_attr(LibSample, 'method2', sample_property)
        self.assert_attr(LibSample, '_decorated_methods',
                         value={'method2': LibSample.method2.method})
        self.assert_attr(TestSample, 'method', sample_property)
        self.assert_attr(TestSample, '_decorated_methods',
                         value={'method': TestSample.method.method})


if __name__ == '__main__':
    unittest.main()
