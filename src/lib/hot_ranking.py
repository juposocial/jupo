#! coding: utf-8
# pylint: disable-msg=W0311
"""
Reddit's Hotranking
http://amix.dk/blog/post/19588

Pure Python implementation
Pyrex version: https://github.com/reddit/reddit/blob/master/r2/r2/lib/db/_sorts.pyx
"""

from datetime import datetime
from math import log

epoch = datetime(1970, 1, 1)

def epoch_seconds(date):
  """Returns the number of seconds from the epoch to date."""
  td = date - epoch
  return td.days * 86400 + td.seconds + (float(td.microseconds) / 1000000)

def score(ups, downs):
  return ups - downs

def hot(ups, downs, date):
  """The hot formula. Should match the equivalent function in postgres."""
  s = score(ups, downs)
  order = log(max(abs(s), 1), 10)
  sign = 1 if s > 0 else -1 if s < 0 else 0
  seconds = epoch_seconds(date) - 1134028003
  return round(order + sign * seconds / 45000, 7)
  

def get_score(document):
  """
  Post mới, tỷ lệ view:starred cao sẽ lên đầu
  TODO: sử dụng thông tin reshare để tăng điểm ups
  """
  ups = len(document.get('starred', [])) * 1000
  downs = len(document.get('read_receipts', []))
  date = datetime.fromtimestamp(document.get('last_updated', 
                                             document.get('timestamp', 0)))
  return hot(ups, downs, date)
  
