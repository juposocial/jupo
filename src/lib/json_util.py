"""

Example usage (serialization)::

>>> json.dumps(..., default=json_util.default)

"""

import calendar
import datetime
import uuid



def default(obj):
    if isinstance(obj, long):
        return str(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, datetime.datetime):
        # TODO share this code w/ bson.py?
        millis = int(calendar.timegm(obj.timetuple()) * 1000 +
                     obj.microsecond / 1000)
        return millis
    raise TypeError("%r is not JSON serializable" % obj)
