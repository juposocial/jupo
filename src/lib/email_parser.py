#! coding: utf-8

from email_reply_parser import EmailReplyParser as reply_parser_1

import re
import email

import lxml.html
import htmlentitydefs
from pyquery import PyQuery


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

def unescape(text):
  def fixup(m):
    text = m.group(0)
    if text[:2] == "&#":
      # character reference
      try:
        if text[:3] == "&#x":
          return unichr(int(text[3:-1], 16))
        else:
          return unichr(int(text[2:-1]))
      except ValueError:
        pass
    else:
      # named entity
      try:
        text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
      except KeyError:
        pass
    return text # leave as is
  return re.sub("&#?\w+;", fixup, text)

def fix_unclosed_tags(html):
  if not html:
    return html
  
  try:
    html = unicode(html)
  except UnicodeDecodeError:
    pass
 
  h = lxml.html.fromstring(html)
  out = lxml.html.tostring(h)
  return unescape(out)
 

def get_text(html):
  """
  Strip signatures and replies from emails
  """
  
  separators = [
    '<div class="gmail_extra">',
    'class="moz-signature"',
    '<div class="gmail_quote">',
    '<div><br></div><div>--&nbsp;</div>',
    '<div>--&nbsp;</div>',
    '<div>-- <br>',
    '<div><br></div>-- </div>',
    '-- <br>',
    '>---<br>',
    '<br clear="all"><div><div><br></div>'
  ]
  
  for separator in separators:
    if separator in html:
      print separator
      html = html.split(separator, 1)[0]
      
  if 'MsoNormal' in html:
    if "From:" in html:
      html = html.split('>From:</', 1)[0]
    if ';border-top:solid' in html:
      html = html.split(';border-top:solid', 1)[0]
  lines = []
  for line in html.split('\n'):
    if '<br>' in line:
      lines.extend([i + '<br>' for i in line.split('<br>')])
    elif '<br/>' in line:
      lines.extend([i + '<br/>' for i in line.split('<br/>')])
    elif '<br />' in line:
      lines.extend([i + '<br />' for i in line.split('<br />')])
    elif '</p>' in line:
      lines.extend([i + '</p>' for i in line.split('</p>')])
    else:
      lines.append(line)
      
  message_lines = []
  for line in lines:
    if '-----Original Message-----' in line:
      break
    elif '________________________________' in line:
      break
    elif '---------------------' in line:
      break
    elif '>---<br>' in line:  # Outlook
      break
    elif 'From:' in line:
      break
    elif 'best regards' in line.lower():
      break
    elif 'Sent from ' in line:
      break
    elif re.findall("On .*?, .*? wrote:", line):
      break
    elif re.findall('[0-9]{4}/\d+/\d+ .*? <\w+@\w+\.\w+>', line):
      break
    else:
      message_lines.append(line)
  html = '\n'.join(message_lines)
  if 'MsoNormal' in html:
    doc = PyQuery(html)
    doc('head').remove()
    doc('.MsoNormal span[style]').attr('style', None)
    doc('.MsoListParagraph[style]').attr('style', None)
    return doc.html().replace('<p> </p>', '')
  else:
    html = fix_unclosed_tags(html.strip())
    return html
  


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
  message_plain_text = None
  message_plain_html = None
  if msg.get_content_maintype() == 'text':
    message = msg.get_payload(decode=True)
  elif msg.get_content_maintype() == 'multipart': #If message is multi part we only want the text version of the body, this walks the message and gets the body.
    for part in msg.walk():       
      if part.get_content_type() == "text/plain":
        message_plain_text = part.get_payload(decode=True)
      elif part.get_content_type() == 'text/html':
        message_plain_html = part.get_payload(decode=True)
      else:
        continue
  else:
    return False, msg_type
  
  message_plain_text = get_text(message_plain_text).strip()
  
  if message_plain_text and message_plain_html:
    if len(message_plain_text) < 500:
      message = message_plain_text
    else:
      message = message_plain_html
      msg_type = 'text/html'
      
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



if __name__ == '__main__':
  f = open('test1.txt')
  data = f.read()
  f.close()
  print get_reply_text(data)
  
  
