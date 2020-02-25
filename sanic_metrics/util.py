# -*- coding: utf-8 -*-
#
import collections.abc
from datetime import datetime, timezone

# https://stackoverflow.com/a/3233356/3121813
def recursive_update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = recursive_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

def datetime_to_iso(_d, include_micros=None):
    """
    :param datetime _d:
    :param bool include_micros:
    :return:
    """
    _d = _d.astimezone(timezone.utc)
    if include_micros is None:
        include_micros = _d.microsecond != 0
    if include_micros:
        return _d.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        return _d.strftime("%Y-%m-%dT%H:%M:%SZ")
