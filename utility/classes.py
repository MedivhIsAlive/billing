from typing import Type, Any, Optional, Callable


class classproperty(property):
    """
    Inherits from property descriptor, which provides fget, fset etc as shown in documentation
    https://docs.python.org/3/howto/descriptor.html

    Updates default __get__ behavior
    by making it pass in class instead of an instance into a fget method ON attribute access
    thus creating a sort of class property
    """
    fget: Callable

    def __get__(self, owner_self: Any, owner_cls: Optional[Type[Any]] = None):
        if not owner_cls:
            raise ValueError("Cannot access classproperty without class object")
        return self.fget(owner_cls)

