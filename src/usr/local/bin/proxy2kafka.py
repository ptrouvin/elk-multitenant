#!/usr/bin/python
#
# Author: pascal Trouvin <pascal.trouvin@o4s.fr>
#
# inspired from: https://gist.github.com/majek/1662475
#
# * Copyright 2015 Pascal TROUVIN <pascal.trouvin at o4s.fr>.
# *
# * Licensed under the Apache License, Version 2.0 (the "License");
# * you may not use this file except in compliance with the License.
# * You may obtain a copy of the License at
# *
# *      http://www.apache.org/licenses/LICENSE-2.0
# *
# * Unless required by applicable law or agreed to in writing, software
# * distributed under the License is distributed on an "AS IS" BASIS,
# * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# * See the License for the specific language governing permissions and
# * limitations under the License.
# *
#
# requirements:
# - kafka-python https://github.com/mumrah/kafka-python  doc http://kafka-python.readthedocs.org/en/latest/usage.html
#
# usage: look at ad-hoc function
#
# History:
# 2015-09-25 pt: 1st release
# 
import asyncore
import errno
import os
import os.path
import socket
import logging
import threading
import sys

sys.path.append(os.path.dirname(sys.argv[0]))

from kafka import SimpleProducer, KafkaClient
from kafka.common import ConnectionError, KafkaUnavailableError

log = logging.getLogger('proxy2kafka')

_map = {}

LOGGING_LEVELS = {'critical': logging.CRITICAL,
                  'error': logging.ERROR,
                  'warning': logging.WARNING,
                  'info': logging.INFO,
                  'debug': logging.DEBUG}

def is_method(obj, name):
    return hasattr(obj, name) and callable(getattr(obj, name))
                                  
class Sock(asyncore.dispatcher):
    def __init__(self, sock, other=None, topic=None, map=None):
        self.other=other
        self.topic=topic
        asyncore.dispatcher.__init__(self, sock, map=map)
    
    def handle_read(self):
        data= self.recv(4096*4)
        if len(data)==0:
            self.close()
        else:
            self.other.send_messages(self.topic, data)

    def handle_close(self):
        log.info(' [-] %i -> %i (closed)' % \
                     (self.getsockname()[1], self.getpeername()[1]))
        self.close()

class Server(asyncore.dispatcher):
    def __init__(self, port, other, topic, map=None):
        self.port = port
        self.map = map
        self.other = other
        self.topic=topic
        asyncore.dispatcher.__init__(self, map=self.map)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('0.0.0.0', port))
        log.info(' [*] TCP Listening %i -> kafka/%s' % \
                     (self.port, self.topic))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if not pair:
            return
        left, addr = pair
        log.info(' [+] %i -> %i' % \
                (addr[1], self.port))
        Sock(left, self.other, self.topic, map=self.map)

    def close(self):
        log.info(' [*] Closed %i' % \
                     (self.port))
        asyncore.dispatcher.close(self)


class UDPServer(asyncore.dispatcher):
    def __init__(self, port, other, topic, map=None):
        self.port = port
        self.other = other
        self.topic=topic
        self.map = map
        asyncore.dispatcher.__init__(self, map=self.map)
        self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.set_reuse_addr()
        self.bind(('0.0.0.0', port))
        log.info(' [*] UDP Listening %i -> kafka/%s' % \
                     (self.port, self.topic))

    def writable(self):
        return False

    def handle_read(self):
        data, client= self.recvfrom(4096*4)
        log.debug(" [+] UDP %s -> %i  : (%d)%s" % (str(client), self.port, len(data), data))
        if len(data)!=0:
            if self.other:
                self.other.send_messages(self.topic, data)

    def handle_close(self):
        log.info(' [-] %i -> %i (closed)' % \
                     (self.getsockname()[1], self.getpeername()[1]))
        self.close()

    def close(self):
        log.info(' [*] Closed %i' % \
                     (self.port))
        asyncore.dispatcher.close(self)

    def __str__(self):
        return 'udp://localhost:%s' % (self.port)

if __name__ == '__main__':
    import argparse
    import time

    parser = argparse.ArgumentParser(description='TCP Proxy messages to kafka MQ')
    parser.add_argument('-l', '--listen-tcp', action='append',
            help='Define a TCP listener port. --listen-tcp=port[/topic]')
    parser.add_argument('-u', '--listen-udp', action='append',
            help='Define a UDP listener port. --listen-udp=port[/topic]')
    parser.add_argument('-k', '--kafka', default='127.0.0.1:9092',
            help='Define the Kafka server, syntax: host[:port][,host2[:port]] , default= 127.0.0.1:9092')
    parser.add_argument('-t', '--topic', default='logstash',
            help='Define the Kafka default topic, default= logstash')
    parser.add_argument('--logging-level', default='info', 
            help='Logging level '+','.join(LOGGING_LEVELS.keys()))
    parser.add_argument('-d', '--daemon', action='store_true',
            help='daemonize')
    parser.add_argument('-U', '--user', 
            help='define the user to start the process with, think about user privilege:  setcap "cap_net_bind_service=+ep" %s' % sys.argv[0])
    
    args = parser.parse_args()
    logging_level = LOGGING_LEVELS.get(args.logging_level, logging.NOTSET)
    logging.basicConfig(level=logging_level,
                      format='%(asctime)s %(levelname)s: %(message)s',
                      datefmt='%Y-%m-%d %H:%M:%S')

    if not args.listen_tcp:
        args.listen_tcp=[514, 9012, 55095, 55096]
    if not args.listen_udp:
        args.listen_udp=[514]
    
    print args
    
    if args.daemon:
        try:
            pid = os.fork()
            if (pid > 0):
                log.info("Daemon started PID(%d)" % pid)
                sys.exit(0) # Parent process exit
        except OSError, e:
            log.error("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror))
            sys.exit(1)
        
        # inside child
        os.umask(0)
        
        if is_method(os, 'setsid'):
            try:
                os.setsid() # cut the link to parent
            except Exception as e:
                log.error("os.setsid() failed: %s" % (str(e)))
        else:
            log.error("Platform ddoes not support os.setsid")
        
    if args.user:
        if not is_method(os, 'setuid'):
            log.error("Platform does not support os.setuid")
        else:
            import pwd
            try:
                uid=pwd.getpwnam(args.user).pw_uid
                log.info("Switch to user '%s(%d)'" % (args.user, uid))
                try:
                    os.setuid(uid)
                except Exception as e:
                    log.error("os.setuid(%d) failed: %s" % (uid, str(e)))
            except Exception as e:
                log.error("pwd.getpwnam(%s) failed %s" % (args.user, str(e)))
    
    log.debug("Starting as user(%d)" % os.getuid())

    if True:
        log.info("Opening connection to Kafka Server")
        while True:
            try:
                kafka = KafkaClient(args.kafka)
                break
            except Exception as e:
                log.error("Connection error, retry in few seconds %s" % str(e))
                time.sleep(60)
                
        producer = SimpleProducer(kafka, async=True)
    else:
        log.info("Kafka connection disabled")
        producer=None
    
    for p in args.listen_tcp:
        try:
            (port,topic) = p.split('/')
        except:
            port=p
            topic=args.topic
        Server(int(port), producer, topic, map=_map)
    for p in args.listen_udp:
        try:
            (port,topic) = p.split('/')
        except:
            port=p
            topic=args.topic
        UDPServer(int(port), producer, topic, map=_map)
    
    asyncore.loop(map=_map,use_poll=True)
    #asyncore.loop(map=_map,use_poll=False)
    
    log.debug("Ending")
