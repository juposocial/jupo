#! coding: utf-8
# pylint: disable-msg=W0311, E0611, E1101
# @PydevCodeAnalysisIgnore
import time
import sys
sys.path.append('../src/')

import api
import models
import settings
import app
from smtplib import SMTP
from unidecode import unidecode
from email.message import Message as EmailMsg
from email.header import Header
from email.MIMEText import MIMEText
import time



TIME_LOGIN = 84600 * 14


def send_mail_user_non_active(skip_index, limit_number):
  info_users = db.owner.find({'is_unremind':{'$ne': 'true'}}).skip(skip_index).limit(limit_number)
  for info_user in info_users:
    info_user = models.User(info_user)
    if int(time.time() - info_user.timestamp) > TIME_LOGIN:
      
      api.send_mail_queue.enqueue(api.send_mail, str(info_user.email),
                                  mail_type='non_active',
                                  receiver_name=info_user.name,
                                  receiver_id=info_user.id)
       
      db.owner.update({'_id': long(info_user.id)},{'$set':{'timestamp': time.time()}})
      
if __name__ == '__main__':
  while True:
    db_names = api.get_database_names()
    for db_name in db_names:
      db = api.DATABASE[db_name]
      skip_index = 0
      limit_number = 50
      count = db.owner.count()
      while(limit_number <= count):
        send_mail_user_non_active(skip_index, limit_number)
        skip_index += 50
        limit_number += 50
        time.sleep(3 * 60)
        
    time.sleep(846000)



