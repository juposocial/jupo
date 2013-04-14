#! coding: utf-8
# pylint: disable-msg=W0311
import sys
import time

sys.path.append('../src/')
from api import DATABASE, add_index, update_index, INDEX, get_attachment_info, Feed

for db_name in DATABASE.database_names():
  try:
    print INDEX.delete_index(db_name)
  except:
    continue
  
for db_name in DATABASE.database_names():
  print db_name
  db = DATABASE[db_name]
  for i in db.stream.find():
    record = Feed(i)
    if record.is_note():
      content = record.details.content
      type_ = 'doc'
    elif record.is_event():
      content = i['name'] + '\n' + i.get('details', '')
      type_ = 'event'
    elif record.is_task():
      content = i.get('message')
      type_ = 'task'
    elif record.is_email():
      content = i.get('email')
      type_ = 'email'
    elif record.is_file():
      content = record.details.name
      type_ = 'file'
    else:
      content = i.get('message')
      type_ = 'post'
    record_id = str(i.get('_id'))
    viewers = i.get('viewers', [])
      
      
    res = add_index(record_id, content, viewers, type_, db_name)
    
    
    if i.has_key('comments'):
      for comment in i['comments']:
        if not i.has_key('owner'):
          continue
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
      
  