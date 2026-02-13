from typing import Type, Any, Optional, Callable


class classproperty(property):
    fget: Callable

    def __get__(self, owner_self: Any, owner_cls: Optional[Type[Any]] = None):
        assert owner_cls, "Cannot access classproperty without class object"
        return self.fget(owner_cls)


__all__ = ("classproperty",)
