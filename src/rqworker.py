#!/usr/bin/env python
#! coding: utf-8
# pylint: disable-msg=W0311

import sys
reload(sys)
sys.setdefaultencoding("utf-8")

  
import api
import settings
from raven import Client as Sentry
from rq import Queue, Worker, Connection
from rq.contrib.sentry import register_sentry


SENTRY = Sentry(settings.SENTRY_DSN)

with Connection(api.TASKQUEUE):
  qs = map(Queue, sys.argv[1:]) or [Queue('default')]
  w = Worker(qs, default_result_ttl=0)
  register_sentry(SENTRY, w)
  w.work()
