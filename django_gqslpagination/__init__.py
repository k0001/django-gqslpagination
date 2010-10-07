# -*- coding: utf8 -*-

from itertools import groupby

from django.core.paginator import EmptyPage
from django.db.models import Count
from django.utils.translation import ugettext_lazy as _


__all__ = 'GroupedQuerySetLaxPage', 'GroupedQuerySetLaxPaginator', 'EmptyPage'


class GroupedQuerySetLaxPage(object):
    def __init__(self, qs, number, paginator, pagination, groups_counts,
                 grouping_field_name):
        self.object_list = qs
        self.number = number
        self.paginator = paginator
        self._pagination = pagination
        self.groups_counts = groups_counts
        self.grouping_field_name = grouping_field_name

    def has_next(self):
        return 'next' in self._pagination

    def has_previous(self):
        return 'previous' in self._pagination

    def has_other_pages(self):
        return self.has_previous() or self.has_next()

    def next_page_number(self):
        return self._pagination['next']

    def previous_page_number(self):
        return self._pagination['previous']

    @property
    def grouped(self):
        return groupby(self.object_list,
                       lambda x: getattr(x, self.grouping_field_name))


class GroupedQuerySetLaxPaginator(object):
    """
    Paginator returning pages of sorted and grouped objects (i.e, GROUP BY).

    The number of objects on a page will be as close as `lax_want` as
    possible. Items from a same group are always on a same page. A single
    page can have items belonging to more than one group.
    """

    def __init__(self, qs, grouping_field_name, lax_want=25, lax_threshold=0.5,
                 reverse=False):
        """
        qs : QuerySet
            QuerySet to paginate

        grouping_field_name : str, unicode
            Name of the grouping field

        lax_want : int
            Number of ideal objects per page

        lax_threshold : float
            If the exceding number of actual objects selected for a page is over
            `lax_threshold` times `lax_want`, then ignore the last selected
            group from the page.

        reverse : bool
            Paginate backwards (i.e, the "greatest" group at the begining).
        """
        assert lax_want > 0
        assert lax_threshold >= 0

        self._qs = qs
        self._grouping_field_name = grouping_field_name
        self._lax_want = lax_want
        self._lax_threshold = lax_threshold
        self._lax_max = lax_want + (lax_want * lax_threshold)
        self._reverse = reverse
        if reverse:
            self._forwards_lookup = '%s__lte' % grouping_field_name
            self._forwards_order = '-%s' % grouping_field_name
            self._forwards_end_lookup = '%s__gte' % grouping_field_name
            self._backwards_lookup = '%s__gt' % grouping_field_name
            self._backwards_order = grouping_field_name
        else:
            self._forwards_lookup = '%s__gte' % grouping_field_name
            self._forwards_order = grouping_field_name
            self._forwards_end_lookup = '%s__lte' % grouping_field_name
            self._backwards_lookup = '%s__lt' % grouping_field_name
            self._backwards_order = '-%s' % grouping_field_name

    def page(self, number=None):
        if number is None:
            try:
                number = self._qs.values_list(self._grouping_field_name) \
                                 .order_by(self._forwards_order)[0:1].get()[0]
            except self._qs.model.DoesNotExist:
                pass
            else:
                if number is None:
                    raise ValueError(u"%s doesn't support NULL values in pagination" % self.__class__.__name__)

        forwards_qs = self._qs.values_list(self._grouping_field_name) \
                              .annotate(Count(self._grouping_field_name)) \
                              .filter(**{self._forwards_lookup: number}) \
                              .order_by(self._forwards_order)

        backwards_qs = self._qs.values_list(self._grouping_field_name) \
                               .annotate(Count(self._grouping_field_name)) \
                               .filter(**{self._backwards_lookup: number}) \
                               .order_by(self._backwards_order)


        # We need to find these grouping values:
        # ..., prev, [start, ..., end], next, ...
        pagination = {}

        lax_count = 0
        for i,(grouping_value,value_count) in enumerate(forwards_qs.iterator()):

            if self._lax_threshold and lax_count > self._lax_max:
                # [AAA]
                # We have exceded the lax treshold, let's use the current group
                # as `nex` and the previous one (if any) as `end`
                if not end is start:
                    end, nex = end_prev, end
                    break

            if lax_count >= self._lax_want:
                # If we get here, it means we have already found `start` and
                # `end` we are looking for `next` now.
                # There's no way we are entering here on the first iteration.
                # Maybe we don't even get here; meaning there's no next page.
                nex = grouping_value
                break

            if i == 0:
                # we are always entering here on the first iteration (if any)
                start = end = grouping_value

            # If we later exced the lax threshold, this will be `end`. See [AAA]
            end_prev = end

            # We always keep the last iterated grouping_value (if any) as `end`
            end = grouping_value

            lax_count += value_count


        else:
            try:
                pagination['start'] = start
            except NameError:
                raise EmptyPage(_(u"%s is not a valid page") % repr(number))
            pagination['end'] = end

        try:
            pagination['next'] = nex
        except NameError:
            pass # we don't have a next page

        try:
            pagination['previous'] = backwards_qs[0:1].get()[0]
        except backwards_qs.model.DoesNotExist:
            pass # we don't have a prev page

        object_list = self._qs.filter(**{self._forwards_lookup: start,
                                         self._forwards_end_lookup: end}) \
                              .order_by(self._forwards_order)

        groups_counts = forwards_qs.filter(**{self._forwards_end_lookup: end})

        return GroupedQuerySetLaxPage(object_list, number, self, pagination,
                                      groups_counts, self._grouping_field_name)

    @property
    def count(self):
        return self._qs.count()
