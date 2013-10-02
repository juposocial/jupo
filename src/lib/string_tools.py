#! coding: utf-8

import re
from unidecode import unidecode

def slugify_ext(message):
  #SO: http://stackoverflow.com/questions/5574042/string-slugification-in-python
  message = unidecode(message).lower()
  return re.sub(r'\W+','-',message)
  