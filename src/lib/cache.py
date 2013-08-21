
from memcache import Client
from hashlib import md5
import settings

MEMCACHED = Client(settings.MEMCACHED_SERVERS)


def _get_version(namespace):
  key = str(namespace)
  version = MEMCACHED.get(key)
  if not version:
    version = 1
    MEMCACHED.set(key, 1)
  return version


def set(key, value, expire=86400, namespace=None):
  if namespace:
    version = _get_version(namespace)
    key = md5('%s|%s|%s' % (namespace, version, key)).hexdigest()
  else:
    key = md5(key).hexdigest()
  if expire:
    MEMCACHED.set(key, value, expire)
  else:
    MEMCACHED.set(key, value)
  return True


def get(key, namespace=None):
  if namespace:
    version = _get_version(namespace)
    key = md5('%s|%s|%s' % (namespace, version, key)).hexdigest()
  else:
    key = md5(key).hexdigest()
  return MEMCACHED.get(key)


def clear(namespace):
  try:
    MEMCACHED.incr(str(namespace))
    return True
  except ValueError:  # MEMCACHED.get(str(namespace)) == None
    return False


def delete(key, namespace=None):
  if namespace:
    version = _get_version(namespace)
    key = md5('%s|%s|%s' % (namespace, version, key)).hexdigest()
  else:
    key = md5(key).hexdigest()
  return MEMCACHED.delete(key)
  