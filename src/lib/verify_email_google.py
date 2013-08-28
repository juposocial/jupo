import DNS
from validate_email import validate_email


def check_google_email(email):
  hostname = email[email.find('@')+1:]
  mx_hosts = DNS.mxlookup(hostname)
  check_google_mail = False
  for mx in mx_hosts:
    _, host_server = mx
    if 'google' in str(host_server).lower() and 'aspmx' in str(host_server).lower():
      check_google_mail = True
  
  if check_google_mail:
    return validate_email(email, verify=True)
  
  else:
    return False
  
