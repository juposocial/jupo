import DNS
import re
from validate_email import validate_email
from DNS.Lib import PackError


EMAIL_RE = re.compile('^[a-zA-Z0-9\.\@]+$')

def is_valid_email(email):
  if email.count('@') != 1:
    return False
  return bool(EMAIL_RE.match(email))

def is_google_apps_email(email):
  if not is_valid_email(email):
    return False
  
  hostname = email[email.find('@')+1:]
  
  try:
    mx_hosts = DNS.mxlookup(hostname)
  except DNS.ServerError as e:
    return False
  except PackError as e:
    return False
  
  for mx in mx_hosts:
    if len(mx) == 2:
      priority, host_server = mx
    else:
      host_server = mx
    if 'google' in str(host_server).lower() and 'aspmx' in str(host_server).lower():
      return True
    
  return False

