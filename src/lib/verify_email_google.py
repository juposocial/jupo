import re
import smtplib
import socket

try:
  import DNS
  ServerError = DNS.ServerError
except:
  DNS = None
  class ServerError(Exception): pass
WSP = r'[ \t]'
CRLF = r'(?:\r\n)'                              
NO_WS_CTL = r'\x01-\x08\x0b\x0c\x0f-\x1f\x7f'     
QUOTED_PAIR = r'(?:\\.)'                          
FWS = r'(?:(?:' + WSP + r'*' + CRLF + r')?' + \
            WSP + r'+)'                        
CTEXT = r'[' + NO_WS_CTL + \
                r'\x21-\x27\x2a-\x5b\x5d-\x7e]'
CCONTENT = r'(?:' + CTEXT + r'|' + \
                     QUOTED_PAIR + r')'        
                                               
COMMENT = r'\((?:' + FWS + r'?' + CCONTENT + \
                    r')*' + FWS + r'?\)'      
CFWS = r'(?:' + FWS + r'?' + COMMENT + ')*(?:' + \
             FWS + '?' + COMMENT + '|' + FWS + ')'
ATEXT = r'[\w!#$%&\'\*\+\-/=\?\^`\{\|\}~]'        
ATOM = CFWS + r'?' + ATEXT + r'+' + CFWS + r'?'   
DOT_ATOM_TEXT = ATEXT + r'+(?:\.' + ATEXT + r'+)*'
DOT_ATOM = CFWS + r'?' + DOT_ATOM_TEXT + CFWS + r'?'
QTEXT = r'[' + NO_WS_CTL + \
                r'\x21\x23-\x5b\x5d-\x7e]'          
QCONTENT = r'(?:' + QTEXT + r'|' + \
                     QUOTED_PAIR + r')'                
QUOTED_STRING = CFWS + r'?' + r'"(?:' + FWS + \
                                r'?' + QCONTENT + r')*' + FWS + \
                                r'?' + r'"' + CFWS + r'?'
LOCAL_PART = r'(?:' + DOT_ATOM + r'|' + \
                         QUOTED_STRING + r')'          
DTEXT = r'[' + NO_WS_CTL + r'\x21-\x5a\x5e-\x7e]'   
DCONTENT = r'(?:' + DTEXT + r'|' + \
                     QUOTED_PAIR + r')'             
DOMAIN_LITERAL = CFWS + r'?' + r'\[' + \
                                 r'(?:' + FWS + r'?' + DCONTENT + \
                                 r')*' + FWS + r'?\]' + CFWS + r'?' 
DOMAIN = r'(?:' + DOT_ATOM + r'|' + \
                 DOMAIN_LITERAL + r')'           
ADDR_SPEC = LOCAL_PART + r'@' + DOMAIN           

VALID_ADDRESS_REGEXP = '^' + ADDR_SPEC + '$'

def validate_email(email, check_mx=False,verify=False):
  try:
    assert re.match(VALID_ADDRESS_REGEXP, email) is not None
    check_mx |= verify
    if check_mx:
      if not DNS: raise Exception('For check the mx records or check if the email exists you must have installed pyDNS python package')
      DNS.DiscoverNameServers()
      hostname = email[email.find('@')+1:]
      mx_hosts = DNS.mxlookup(hostname)
      check_google_mail = False
      for mx in mx_hosts:
        _, host_server = mx
        if 'google' in str(host_server).lower():
          check_google_mail = True
      if check_google_mail:
        check_google_mail = True
        for mx in mx_hosts:
          try:
            smtp = smtplib.SMTP()
            smtp.connect(mx[1])
            if not verify: return True
            status, _ = smtp.helo()
            if status != 250: continue
            smtp.mail('')
            status, _ = smtp.rcpt(email)
            if status != 250: return False
            break
          except smtplib.SMTPServerDisconnected:
            break
          except smtplib.SMTPConnectError:
            continue
      else:
        return False
  except (AssertionError, ServerError): 
    return False
  return True

if __name__ == '__main__':
  print validate_email('zen1@jupo.com', verify=True)