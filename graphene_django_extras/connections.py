from collections import Iterable
from functools import partial
from django.db.models import QuerySet, Manager
from graphene import NonNull, Int, String, Argument
from graphene.relay.connection import IterableConnectionField, PageInfo
from graphene.utils.thenables import maybe_thenable
from graphene_django import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField
from graphql_relay.connection.arrayconnection import connection_from_array_slice
from graphene_django_extras.settings import graphql_api_settings
from graphene_django_extras.utils import queryset_refactor, _get_queryset


class ConnectionField(IterableConnectionField):
    def __init__(self, type, *args, **kwargs):
        super(ConnectionField, self).__init__(type, *args, **kwargs)
        self.args["first"] = Int(default_value=graphql_api_settings.DEFAULT_PAGE_SIZE)

    @classmethod
    def resolve_connection(cls, connection_type, args, resolved):
        if isinstance(resolved, connection_type):
            return resolved

        assert isinstance(resolved, Iterable), (
            "Resolved value from the connection field have to be iterable or instance of {}. "
            'Received "{}"'
        ).format(connection_type, resolved)

        if isinstance(resolved, QuerySet):
            _len = resolved.count()
        else:
            _len = len(resolved)
        connection = connection_from_array_slice(
            resolved,
            args,
            slice_start=0,
            list_length=_len,
            list_slice_length=_len,
            connection_type=connection_type,
            edge_type=connection_type.Edge,
            pageinfo_type=PageInfo,
        )
        connection.iterable = resolved
        return connection

    @classmethod
    def connection_resolver(cls, resolver, connection_type, root, info, **args):
        resolved = resolver(root, info, **args)

        if isinstance(connection_type, NonNull):
            connection_type = connection_type.of_type

        if not resolved and getattr(connection_type, 'resolve_objects', None):
            resolved = connection_type.resolve_objects(root, info, **args)

        on_resolve = partial(cls.resolve_connection, connection_type, args)
        return maybe_thenable(resolved, on_resolve)


class DjangoConnectionPageLimitField(DjangoConnectionField):
    def __init__(self,
                 type,
                 order_by=None,
                 *args,
                 **kwargs):
        kwargs.setdefault('ordering', String(default_value=order_by) if order_by else String())
        super(DjangoConnectionPageLimitField, self).__init__(type, *args, **kwargs)
        self.args["first"] = Argument(Int, default_value=graphql_api_settings.DEFAULT_PAGE_SIZE)

    def resolve_queryset(self, connection, queryset, info, args, **kwargs):
        order = args.get('ordering')
        qs = super(DjangoConnectionPageLimitField, self).resolve_queryset(connection, queryset, info, args, **kwargs)

        if isinstance(qs, Manager):
            qs = self.get_queryset(queryset)

        is_queryset = isinstance(qs, QuerySet)

        if is_queryset:
            qs = queryset_refactor(qs, info.field_nodes, fragments=info.fragments, **kwargs)

        if order and is_queryset:
            if "," in order:
                order = order.strip(",").replace(" ", "").split(",")
                if order.__len__() > 0:
                    qs = qs.order_by(*order)
            else:
                qs = qs.order_by(order)

        return qs

    @classmethod
    def get_queryset(cls, manager):
        return _get_queryset(manager)


class DjangoFilterConnectionPageLimitField(DjangoConnectionPageLimitField, DjangoFilterConnectionField):
    def __init__(self, type, order_by=None, *args, **kwargs):
        kwargs.setdefault('first', Int(default_value=graphql_api_settings.DEFAULT_PAGE_SIZE))
        super(DjangoFilterConnectionPageLimitField, self).__init__(type, *args, **kwargs)
