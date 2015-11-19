from functools import wraps, partial
import rest_framework.views
from django_validator.converters import ConverterRegistry
from django_validator.exceptions import ValidationError
from django_validator.validators import ValidatorRegistry


def _get_lookup(request, name, default, kwargs):
    # Try to be compatible with older django rest framework.
    if hasattr(request, 'query_params'):
        return request.query_params.get(name, default)
    else:
        return request.GET.get(name, default)


def _post_lookup(request, name, default, kwargs):
    if hasattr(request, 'data'):
        return request.data.get(name, default)
    elif hasattr(request, 'DATA'):
        return request.DATA.get(name, default)
    else:
        return request.POST.get(name, default)


def _post_or_get_lookup(request, name, default, kwargs):
    if hasattr(request, 'data'):
        value = request.data.get(name)
    elif hasattr(request, 'DATA'):
        value = request.DATA.get(name)
    else:
        value = request.POST.get(name)
    return value if value is not None else _get_lookup(request, name, default, kwargs)


def _header_lookup(request, name, default, kwargs):
    if request is not None and hasattr(request, 'META'):
        return request.META.get(name, default)
    else:
        return default


def _uri_lookup(request, name, default, kwargs):
    return kwargs.get(name, default)


def param(name, related_name=None, default=None, type='string', lookup=_get_lookup, many=False, separator=',',
          validators=None, validator_classes=None):
    return _Param(name, related_name, default, type, lookup, many, separator, validators, validator_classes)


class _Param(object):
    def __init__(self, name, related_name, default, type, lookup, many, separator, validators, validator_classes):
        self.name = name
        self.related_name = related_name if related_name else name
        self.default = default
        self.type = type
        self.lookup = lookup
        self.many = many
        self.separator = separator
        self.validators = ValidatorRegistry.get_validators(validators)
        if validator_classes:
            if hasattr(validator_classes, '__iter__'):
                self.validators.extend(validator_classes)
            else:
                self.validators.append(validator_classes)

    def __call__(self, func):
        if hasattr(func, '__params__'):
            func.__params__.append(self)
            return func

        @wraps(func)
        def _decorator(*args, **kwargs):
            if len(args) < 1:
                # Call function immediately, maybe raise an error is better.
                return func(*args, **kwargs)

            if isinstance(args[0], rest_framework.views.APIView):
                request = args[0].request
            else:
                request = args[0]

            if request:
                # Checkout all the params first.
                for _param in _decorator.__params__:
                    _param._parse(request, kwargs)
                # Validate after all the params has checked out, because some validators needs all the params.
                for _param in _decorator.__params__:
                    for validator in _param.validators:
                        validator(_param.name, kwargs)

            return func(*args, **kwargs)

        _decorator.__params__ = [self]
        return _decorator

    def _parse(self, request, kwargs):
        converter = ConverterRegistry.get(self.type)
        value = self.lookup(request, self.name, self.default, kwargs)
        try:
            if self.many:
                if isinstance(value, str):
                    values = value.split(self.separator)
                else:
                    values = value
                converted_value = [converter.convert(self.name, _value) for _value in values]
            else:
                converted_value = converter.convert(self.name, value)
        except ValidationError as e:
            raise e
        except Exception as e:
            raise ValidationError('Type Convert error: %s' % e.message)

        kwargs[self.related_name] = converted_value


GET = partial(param, lookup=_get_lookup)
POST = partial(param, lookup=_post_lookup)
POST_OR_GET = partial(param, lookup=_post_or_get_lookup)
HEADER = partial(param, lookup=_header_lookup)
URI = partial(param, lookup=_uri_lookup)
