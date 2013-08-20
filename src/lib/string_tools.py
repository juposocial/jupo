#! coding: utf-8

from slugify import slugify #create slug (short name) from string

def slugify_vn(message):
  #SO: http://stackoverflow.com/questions/1605041/django-slug-in-vietnamese
  _map = u"đd ĐD" #mapping from unicode to regular alphabet, "đ" is an exception, to check if there are any other similar exceptions ?
  vietnamese_map = dict((ord(m[0]), m[1:]) for m in _map.split()) #Take the above string and generate a translation dict

  if isinstance(message, str):
    message = unicode(message)
  
  return slugify(message.translate(vietnamese_map))