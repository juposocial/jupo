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

db_name = api.get_database_name()
db = api.DATABASE[db_name]

TIME_LOGIN = 84600 * 14

        
def get_info_users(num, get):
  info_users = db.owner.find({'is_unremind':{'$ne': 'true'}})[num:get]
  for info_user in info_users:
    info_user = models.User(info_user)
    if int(time.time() - info_user.timestamp) > TIME_LOGIN:
      
      api.send_mail_queue.enqueue(api.send_mail, str(info_user.email),
                                  mail_type='forget_login',
                                  receiver_name=info_user.name,
                                  receiver_id=info_user.id)
      
      db.owner.update({'_id': long(info_user.id)},{'$set':{'timestamp': time.time()}})
      
if __name__ == '__main__':
  num = 0
  get = 50
  while(True):
    count = db.owner.count()
    while(get <= count):
      get_info_users(num, get)
      num += 50
      get += 50
      time.sleep(3 * 60)
    time.sleep(846000)


