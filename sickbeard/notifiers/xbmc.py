# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.


import urllib, urllib2
import socket
import base64
import json
import time, struct

import sickbeard

from sickbeard import logger
from sickbeard import common
from sickbeard.exceptions import ex
from sickbeard.encodingKludge import fixStupidEncodings

try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

class XBMCNotifier:

    def notify_snatch(self, ep_name):
        if sickbeard.XBMC_NOTIFY_ONSNATCH:
            self._notifyXBMC(ep_name, common.notifyStrings[common.NOTIFY_SNATCH])

    def notify_download(self, ep_name):
        if sickbeard.XBMC_NOTIFY_ONDOWNLOAD:
            self._notifyXBMC(ep_name, common.notifyStrings[common.NOTIFY_DOWNLOAD])

    def test_notify(self, host, username, password):
        response = self._notifyXBMC("Testing XBMC notifications from Sick Beard", "Test Notification", host, username, password, force=True)
        success = False
        try:
            success = all(json.loads(a['response'])['result'] == 'OK' for a in response)
        except Exception, e:
            print e

        return success

    def update_library(self, show_name):
        if sickbeard.XBMC_UPDATE_LIBRARY:
            for curHost in [x.strip() for x in sickbeard.XBMC_HOST.split(",")]:
                # do a per-show update first, if possible
                if not self._update_library(curHost, showName=show_name) and sickbeard.XBMC_UPDATE_FULL:
                    # do a full update if requested
                    self._update_library(curHost)

    def _username(self):
        return sickbeard.XBMC_USERNAME

    def _password(self):
        return sickbeard.XBMC_PASSWORD

    def _use_me(self):
        return sickbeard.USE_XBMC

    def _hostname(self):
        return sickbeard.XBMC_HOST

    def _sendToXBMC(self, command, host, username=None, password=None):
        '''
        Handles communication with XBMC servers

        command - Dictionary of field/data pairs, encoded via urllib.urlencode and
        passed to /xbmcCmds/xbmcHttp

        host - host/ip + port (foo:8080)
        '''
        command['jsonrpc'] = '2.0'
        command['id'] = 1

        if not username:
            username = self._username()
        if not password:
            password = self._password()

        for key in command:
            if type(command[key]) == unicode:
                command[key] = command[key].encode('utf-8')

        logger.log(u"Encoded command is %s" % command, logger.DEBUG)
        # Web server doesn't like POST, GET is the way to go
        url = 'http://%s/jsonrpc' % host

        try:
            # If we have a password, use authentication
            req = urllib2.Request(url, data=json.dumps(command))

            if password:
                logger.log(u"Adding Password to XBMC url", logger.DEBUG)
                base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
                authheader = "Basic %s" % base64string
                req.add_header("Authorization", authheader)

            req.add_header('Content-type', 'application/json')

            logger.log(u"Contacting XBMC via url: " + url, logger.DEBUG)
            logger.log(u"Contacting XBMC with command: %s" % command, logger.DEBUG)

            handle = urllib2.urlopen(req)
            response = handle.read().decode(sickbeard.SYS_ENCODING)

            logger.log(u"response: " + response, logger.DEBUG)
        except IOError, e:
            logger.log(u"Warning: Couldn't contact XBMC HTTP server at " + fixStupidEncodings(host) + ": " + ex(e))
            response = ''
        except Exception, e:
            logger.log(u"Error: Couldn't send request to XBMC HTTP server at " + fixStupidEncodings(host) + ": " + ex(e))
            response = ''

        return response

    def _notifyXBMC(self, input, title="Sick Beard", host=None, username=None, password=None, force=False):

        if not self._use_me() and not force:
            logger.log("Notification for XBMC not enabled, skipping this notification", logger.DEBUG)
            return False

        if not host:
            host = self._hostname()
        if not username:
            username = self._username()
        if not password:
            password = self._password()

        logger.log(u"Sending notification for " + input, logger.DEBUG)

        result = []

        for curHost in [x.strip() for x in host.split(",")]:
            command = {'method': 'GUI.ShowNotification', 'params': {'title': title, 'message': input}}
            logger.log(u"Sending notification to XBMC via host: " +
                    curHost + "username: " + username +
                    " password: " + password, logger.DEBUG)
            if result:
                result += ', '
            result.append({'host':curHost, 'response':self._sendToXBMC(command, curHost, username, password)})

        return result

    def _update_library(self, host, showName=None):

        if not self._use_me():
            logger.log("Notifications for XBMC not enabled, skipping library update", logger.DEBUG)
            return False

        logger.log(u"Updating library in XBMC", logger.DEBUG)

        if not host:
            logger.log('No host specified, no updates done', logger.DEBUG)
            return False

        # if we're doing per-show
        if showName:
            # Use this to get xml back for the path lookups
            queryCommand = {'method': 'VideoLibrary.GetTVShows', 'params': {'properties': ['file']}}

            # Set xml response format, if this fails then don't bother with the rest
            r = self._sendToXBMC(queryCommand, host)
            if not r:
                return False

            response = json.loads(r)

            #get show
            shows = response['result']['tvshows']

            show = next((x for x in shows if x['label'] == showName), None)

            if show:
                # Don't need it double-encoded, gawd this is dumb
                unEncPath = urllib.unquote(show['file']).decode(sickbeard.SYS_ENCODING)
                logger.log(u"XBMC Updating " + showName + " on " + host + " at " + unEncPath, logger.DEBUG)
                updateCommand = {'method': 'VideoLibrary.Scan', 'params': {'directory': show['file']}}
                request = self._sendToXBMC(updateCommand, host)
                if not request:
                    logger.log(u"Update of show directory failed on " + showName + " on " + host + " at " + unEncPath, logger.ERROR)
                    return False
        else:
            logger.log(u"Do a full update as requested", logger.DEBUG)
            logger.log(u"XBMC Updating " + host, logger.DEBUG)
            updateCommand = {'method': 'VideoLibrary.Scan'}
            request = self._sendToXBMC(updateCommand, host)

            if not request:
                logger.log(u"Full update failed on " + host, logger.ERROR)
                return False

        return True

# Wake function
def wakeOnLan(ethernet_address):
    addr_byte = ethernet_address.split(':')
    hw_addr = struct.pack('BBBBBB', int(addr_byte[0], 16),
    int(addr_byte[1], 16),
    int(addr_byte[2], 16),
    int(addr_byte[3], 16),
    int(addr_byte[4], 16),
    int(addr_byte[5], 16))

    # Build the Wake-On-LAN "Magic Packet"...
    msg = '\xff' * 6 + hw_addr * 16

    # ...and send it to the broadcast address using UDP
    ss = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ss.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    ss.sendto(msg, ('<broadcast>', 9))
    ss.close()

# Test Connection function
def isHostUp(host,port):

    (family, socktype, proto, garbage, address) = socket.getaddrinfo(host, port)[0] #@UnusedVariable
    s = socket.socket(family, socktype, proto)

    try:
        s.connect(address)
        return "Up"
    except:
        return "Down"


def checkHost(host, port):

    # we should try to get this programmatically from the IP
    mac = ""

    i=1
    while isHostUp(host,port)=="Down" and i<4:
        wakeOnLan(mac)
        time.sleep(20)
        i=i+1

notifier = XBMCNotifier
