#! coding: utf-8
# pylint: disable-msg=W0311
import sys
import time

sys.path.append('../src/')
from api import DATABASE, add_index, update_index, es, get_attachment_info, Feed

print es.delete_index('jupo-index')

for i in DATABASE.stream.find():
  record = Feed(i)
  if record.is_note():
    content = record.details.content
    _type = 'doc'
  elif record.is_event():
    content = i['name'] + '\n' + i.get('details', '')
    _type = 'event'
  elif record.is_task():
    content = i.get('message')
    _type = 'task'
  elif record.is_email():
    content = i.get('email')
    _type = 'email'
  elif record.is_file():
    content = record.details.name
    _type = 'file'
  else:
    content = i.get('message')
    _type = 'post'
  record_id = str(i.get('_id'))
  viewers = i.get('viewers')
  try:
    res = add_index(record_id, content, viewers, _type)
  except Exception:
    print '[Exception] %s' % record_id
    print type
    time.sleep(0.5)
    continue
  
  if i.has_key('comments'):
    for comment in i['comments']:
      viewers.append(i['owner'])
      try:
        res = update_index(record_id, 
                     comment['message'], 
                     viewers=list(set(viewers)), 
                     is_comment=True)
      except Exception:
        print '[Exception] %s' % record_id
        time.sleep(0.5)
        continue
  print '[%s] %s' % (res, record_id)
    
  