#! coding: utf-8

from email_reply_parser import EmailReplyParser as reply_parser_1

import re
import email




def get_subject(data):
  msg = email.message_from_string(data)
  return msg['Subject']

def get_reply_and_original_text(data):
  """
  Strip signatures and replies from emails
  http://stackoverflow.com/a/2193937
  
  Drop all text after and including:

  Lines that equal '-- \n' (standard email sig delimiter)
  Lines that equal '--\n' (people often forget the space in sig delimiter; and this is not that common outside sigs)
  Lines that begin with '________________________________' (32 underscores, Outlook agian)
  Lines that begin with 'On ' and end with ' wrote:\n' (OS X Mail.app default)
  Lines that begin with 'From: ' (failsafe four Outlook and some other reply formats)
  Lines that begin with 'Sent from my iPhone'
  Lines that begin with 'Sent from my BlackBerry'
  """
  msg = email.message_from_string(data)
  msg_type = None
  if msg.get_content_maintype() == 'text':
    message = msg.get_payload(decode=True)
  elif msg.get_content_maintype() == 'multipart': #If message is multi part we only want the text version of the body, this walks the message and gets the body.
    for part in msg.walk():       
      if part.get_content_type() == "text/plain":
        message = part.get_payload(decode=True)
        break
      elif part.get_content_type() == "text/html":
        message = part.get_payload(decode=True)
        msg_type = 'text/html'
        break
      else:
        continue
  else:
    return False, msg_type
  
  msg = message.split('-- \n', 1)[0]
  msg = msg.split('--\n', 1)[0]
  
  lines = msg.split("\n")
  message_lines = []
  for line in lines:
    if line.startswith('________________________________'):
      break
    elif line.startswith('On ') and line.endswith(' wrote:\n'):
      break
    elif line.startswith('From: '):
      break
    elif line.startswith('Sent from '):
      break
    
    # Trường hợp dạng: 2013/1/16 Pham Tuan Anh <anhpt@5works.co> (Gmail)
    elif re.match('[0-9]{4}/[0-9]?[0-2]/[0-9]?[0-9] .*? <\w+@\w+\.\w+>', line):
      break
    else:
      message_lines.append(line)
      
  msg = '\n'.join(message_lines)

  msg = reply_parser_1.parse_reply(msg)
  return msg.strip(), msg_type

def get_reply_text(data):
  """
  Strip signatures and replies from emails
  http://stackoverflow.com/a/2193937
  
  Drop all text after and including:

  Lines that equal '-- \n' (standard email sig delimiter)
  Lines that equal '--\n' (people often forget the space in sig delimiter; and this is not that common outside sigs)
  Lines that begin with '-----Original Message-----' (MS Outlook default)
  Lines that begin with '________________________________' (32 underscores, Outlook agian)
  Lines that begin with 'On ' and end with ' wrote:\n' (OS X Mail.app default)
  Lines that begin with 'From: ' (failsafe four Outlook and some other reply formats)
  Lines that begin with 'Sent from my iPhone'
  Lines that begin with 'Sent from my BlackBerry'
  """
  
  msg = email.message_from_string(data)
  msg_type = None
  message = ''
  if msg.get_content_maintype() == 'text':
    message = msg.get_payload(decode=True)
  elif msg.get_content_maintype() == 'multipart': #If message is multi part we only want the text version of the body, this walks the message and gets the body.
    for part in msg.walk():       
      if part.get_content_type() == "text/plain":
        message = message + part.get_payload(decode=True)
      elif part.get_content_type() == 'text/html':
        message = message + part.get_payload(decode=True)
        msg_type = 'text/html'
      else:
        continue
  else:
    return False, msg_type
  
  msg = message.split('-- \n', 1)[0]
  msg = msg.split('--\n', 1)[0]
  
  lines = msg.split("\n")
  message_lines = []
  for line in lines:
    if line.startswith('-----Original Message-----'):
      break
    elif line.startswith('________________________________'):
      break
    elif line.startswith('On ') and line.endswith(' wrote:\n'):
      break
    elif line.startswith('From: '):
      break
    elif line.startswith('Sent from '):
      break
    
    # Trường hợp dạng: 2013/1/16 Pham Tuan Anh <anhpt@5works.co> (Gmail)
    elif re.match('[0-9]{4}/[0-9]?[0-2]/[0-9]?[0-9] .*? <\w+@\w+\.\w+>', line):
      break
    else:
      message_lines.append(line)
      
  msg = '\n'.join(message_lines)

  msg = reply_parser_1.parse_reply(msg)
  return msg.strip(), msg_type



# if __name__ == '__main__':
#   f = open('test2.txt')
#   data = f.read()
#   f.close()
#   print get_reply_text(data)
  
  
