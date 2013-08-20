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

db = api.DATABASE['play_jupo_dev']
COUNT_PEOPLE = db.owner.count()
TIME_LOGIN = 84600 * 14


def get_unread_notifications(id_receiver):
  notifications = db.notification.find({'receiver': id_receiver,
                                        'is_unread': True})
  
  dict_message = {}
  list_message = []
  dict_message['number'] = notifications.count()
  for notification in notifications:
    notification = dict(notification)
    info_sender = db.owner.find_one({'_id': notification['sender']})
    sender = models.User(info_sender)
    message = {}
    
    message['type'] = notification['type']
    message['sender'] = sender.name
    list_message.append(message)
  dict_message['content'] = list_message
  
  return dict_message
    
def send_email(receiver):
  subject = "Hi %s ,Do you remember Jupo ?" % receiver.name
  dict_message = get_unread_notifications(receiver.id)
  dict_message['name_receiver'] = receiver.name
  dict_message['id_receiver'] = receiver.id
  dict_message['host'] = settings.PRIMARY_DOMAIN
  template = app.CURRENT_APP.jinja_env.get_template('email/forget_login.html')
  body = template.render(receiver=receiver, dict_message=dict_message)
  
  if receiver.email and body:
    msg = MIMEText(body, 'html', _charset="UTF-8")
    msg['Subject']= Header(subject, "utf-8")
    msg['From'] = settings.SMTP_SENDER
    msg['X-MC-Track'] = 'opens,clicks'
    msg['X-MC-Autotext'] = 'true'
    
    MAIL = SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        
    if settings.SMTP_PASSWORD:
      MAIL.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
      
      
    MAIL.sendmail(settings.SMTP_SENDER, 
                  str(receiver.email), msg.as_string())
    
    MAIL.quit()
    
    db.owner.update({'_id': receiver.id},{'$set':{'timestamp': time.time()}})
    time.sleep(1)
    return True
  else:
    return False
        
        
def get_info_users(num, get):
  info_users = db.owner.find({'is_unremind':{'$ne': 'true'}})[num:get]
  for info_user in info_users:
    info_user = models.User(info_user)
    if int(time.time() - info_user.timestamp) > TIME_LOGIN:
      send_email(info_user)

if __name__ == '__main__':
  num = 0
  get = 50
  while(True):
    while(get <= COUNT_PEOPLE):
      get_info_users(num, get)
      num += 50
      get += 50
      time.sleep(3*60)
    time.sleep(846000)
    
    
    
    
