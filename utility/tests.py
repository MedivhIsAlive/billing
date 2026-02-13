from django.test import TestCase

from utility.collections import filtered_dict
from utility.classes import classproperty


class FilteredDictTest(TestCase):

    def test_removes_none_values(self):
        result = filtered_dict({"a": 1, "b": None, "c": 3})
        self.assertEqual(result, {"a": 1, "c": 3})

    def test_empty_dict(self):
        result = filtered_dict({})
        self.assertEqual(result, {})

    def test_all_none(self):
        result = filtered_dict({"a": None, "b": None})
        self.assertEqual(result, {})

    def test_custom_filter(self):
        result = filtered_dict({"a": 1, "b": 2, "c": 3}, key=lambda k, v: v > 1)
        self.assertEqual(result, {"b": 2, "c": 3})

    def test_no_none(self):
        result = filtered_dict({"a": 1, "b": 2})
        self.assertEqual(result, {"a": 1, "b": 2})


class ClasspropertyTest(TestCase):

    def test_classproperty_on_class(self):
        class MyClass:
            _value = 42

            @classproperty
            def value(cls):
                return cls._value

        self.assertEqual(MyClass.value, 42)

    def test_classproperty_on_instance(self):
        class MyClass:
            @classproperty
            def name(cls):
                return cls.__name__

        self.assertEqual(MyClass().name, "MyClass")
