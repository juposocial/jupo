#! coding: utf-8
# pylint: disable-msg=W0311
from werkzeug.routing import BaseConverter

class RegexConverter(BaseConverter):
  def __init__(self, url_map, *items):
    super(RegexConverter, self).__init__(url_map)
    self.regex = items[0]
        
    
class UUIDConverter(BaseConverter):
  def __init__(self, url_map, *items):
    super(UUIDConverter, self).__init__(url_map)
    self.regex = '([A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12})'
        

class SnowflakeIDConverter(BaseConverter):
  def __init__(self, url_map, *items):
    super(SnowflakeIDConverter, self).__init__(url_map)
    self.regex = '(\d+)'
        