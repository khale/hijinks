#!/usr/bin/env python

"""
Copyright 2011 Thomas Graft, http://thomasgraft.com/. All rights reserved.

curses/Mac modifications by Kyle C. Hale 2013

Redistribution and use in source and binary forms, with or without modification, are
permitted provided that the following conditions are met:

   1. Redistributions of source code must retain the above copyright notice, this list of
      conditions and the following disclaimer.

   2. Redistributions in binary form must reproduce the above copyright notice, this list
      of conditions and the following disclaimer in the documentation and/or other materials
      provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THOMAS GRAFT ``AS IS'' AND ANY EXPRESS OR IMPLIED
WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THOMAS GRAFT OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The views and conclusions contained in the software and documentation are those of the
authors and should not be interpreted as representing official policies, either expressed
or implied, of Thomas Graft.

"""
import socket
import hashlib
import urllib2
import sys    
import curses
import re
import time
import threading

class RepeatEvery(threading.Thread):
    def __init__(self, interval, func, *args, **kwargs):
        threading.Thread.__init__(self)
        self.interval = interval  # seconds between calls
        self.func = func          # function to call
        self.args = args          # optional positional argument(s) for call
        self.kwargs = kwargs      # optional keyword argument(s) for call
        self.runable = True
    def run(self):
        while self.runable:
            self.func(*self.args, **self.kwargs)
            time.sleep(self.interval)
    def stop(self):
        self.runable = False


class BoxeeRemote:
    
    def __init__(self):
        
        # Begin User configurable data
        
        # Boxee will tell us this data when it pings us back
        # if this is not None, it will skip the broadcast phase
        self.BOXEE_ADDRESS = None
        self.BOXEE_PORT = None

        # for changing volume (granularity in percentage)
        self.VOL_GRAN = 2
        self.KBD = 0
        self.CURR_OFFSET = 42

        # Debug mode will print things
        # Set to False to avoid printing out messages
        self.DEBUG = False

        # End User configurable data

        # Where we want boxee to ping us back at
        self.UDP_LOCAL_IP = '' # binds to all local interfaces
        self.UDP_LOCAL_PORT = 2563

        # Broadcast port / IP for when we look for Boxee
        self.UDP_BOXEE_BROADCAST = ('<broadcast>', 2562)

        # This is the data we ping Boxee with
        self.BOXEE_APPLICATION = 'iphone_remote' # required for this to work
        self.BOXEE_SHARED_KEY = 'b0xeeRem0tE!'   # required for this to work
        self.BOXEE_CHALLENGE = 'boxee_cmd_client'
        self.BOXEE_VERSION = '0.1' # version of this app, not really used i think
        self.BOXEE_SIGNATURE = hashlib.md5( self.BOXEE_CHALLENGE + self.BOXEE_SHARED_KEY ).hexdigest()

        self.BOXEE_API_URL = "http://%s:%s/xbmcCmds/xbmcHttp?command=%s(%s)"

        self.UDP_MESSAGE_TO_BOXEE = '''<?xml version="1.0"?>
            <BDP1 cmd="discover" 
                  application="%s"
                  version="%s" challenge="%s"
                  signature="%s" />''' % ( self.BOXEE_APPLICATION, self.BOXEE_VERSION, self.BOXEE_CHALLENGE, self.BOXEE_SIGNATURE )
        
        
        # Broadcast for Boxee info if not already set
        if not self.BOXEE_ADDRESS or not self.BOXEE_PORT:
            self.discover();
    
    def discover(self):
        """Discovers and saves info about Boxee device on the network."""
        self._parse_boxee_response( self._broadcast_for_boxee_info() )

    def run_human_command( self, command ):
        """Run a non-formated boxee command, eg "vol 50" """
        self.run_command( self._convert_command( command ) )

    def run_command( self, command, argument=None ):
        """Runs a command against the boxee box. Command must match API syntax, eg SetVolume(50)"""
        url = self.BOXEE_API_URL % ( self.BOXEE_ADDRESS, self.BOXEE_PORT, command, argument )
        res = urllib2.urlopen(url)
        return res.read()

    def _broadcast_for_boxee_info( self ):
        self._status("Broadcasting for Boxee")
        sock = socket.socket( socket.AF_INET, # Internet
                              socket.SOCK_DGRAM ) # UDP

        sock.setsockopt( socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        sock.sendto( self.UDP_MESSAGE_TO_BOXEE, self.UDP_BOXEE_BROADCAST )
        self._status("Done")

        self._status("Awaiting a response from Boxee")
        while True:

            (buf, address) = sock.recvfrom(2048)

            if not len(buf):
                break

            self.BOXEE_ADDRESS = address[0]

            return buf

    def _parse_boxee_response( self, response ):
        """ Parses the discovery response UDP packet XML """
        from xml.dom import minidom

        self._status("Parsing response from Boxee:\n" + response)

        dom = minidom.parseString(response)

        for node in dom.getElementsByTagName('BDP1'):
            self.BOXEE_PORT = node.getAttribute('httpPort')

    def get_cur_vol(self):
        cur = self.run_command('GetVolume')
        m = re.search(r"(<li>)(\d*)", cur)
        return int(m.group(2))


    def _convert_command( self, human ):
        
        shortcut_map = {
            ord('\\'):'SendKey(257)',
            ord('m'):'mute',
            ord('p'):'pause',
            ord('s'):'stop',
            ord('n'):'PlayNext',
            ord('r'):'PlayPrev',
            ord('1'):'Shutdown',
            ord('2'):'Reset',
            ord('>'):'SeekPercentageRelative(1)',
            ord('<'):'SeekPercentageRelative(-1)',

            curses.KEY_UP:'SendKey(270)',
            curses.KEY_DOWN:'SendKey(271)',
            curses.KEY_LEFT:'SendKey(272)',
            curses.KEY_RIGHT:'SendKey(273)',

            # VIM style key bindings
            ord('k'):'SendKey(270)',
            ord('j'):'SendKey(271)',
            ord('h'):'SendKey(272)',
            ord('l'):'SendKey(273)',
            ord('\n'):'SendKey(61453)',
            ord(' '):'SendKey(61453)',

            # backspace/delete
            127:'SendKey(275)',
        }

        if human == ord('`'):
            self.KBD ^= 1
            return human

        if self.KBD == 1:
            if human == 8 or human == 127:
                return 'SendKey(61704)'
            else:
                return 'SendKey(%s)' % (human + 61696)
        
        if human in shortcut_map.keys():
            return shortcut_map[human]
        elif human == ord('u'):
            vol = self.get_cur_vol()
            return 'SetVolume(%s)' % (vol + self.VOL_GRAN)
        elif human == ord('d'):
            vol = self.get_cur_vol()
            return 'SetVolume(%s)' % (vol - self.VOL_GRAN)
            
        
        return human

    def _status( self, msg ):
        if self.DEBUG:
            print msg


def kill_curses(scr):
    curses.nocbreak()
    scr.keypad(0)
    curses.echo()
    curses.endwin()

def update_curr(boxee, scr):
    cur = boxee.run_command('GetCurrentlyPlaying')
    title = re.search(r"(Title:)(.*)", cur)
    artist = re.search(r"(Artist:)(.*)", cur)
    album = re.search(r"(Album:)(.*)", cur)

    curvol = boxee.get_cur_vol()
    for i in range (0,4):
        scr.move(boxee.CURR_OFFSET+i, 0)
        scr.clrtoeol()

    scr.addstr(boxee.CURR_OFFSET + 3, 0, "Volume: %d%%" % curvol, curses.color_pair(3))
    try:
        res = "Currently playing : %s " % title.group(2)
        scr.addstr(boxee.CURR_OFFSET, 0, res, curses.color_pair(2))
        scr.addstr(boxee.CURR_OFFSET+1, 0, 'Artist: %s' % artist.group(2), curses.color_pair(2))
        scr.addstr(boxee.CURR_OFFSET+2, 0, 'Album: %s' % album.group(2), curses.color_pair(2))
    except:
        scr.addstr(boxee.CURR_OFFSET, 0, 'Nothing currently playing', curses.color_pair(2))

def init_colors():
    curses.start_color()
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_BLUE, curses.COLOR_BLACK)

def main():

    USAGE = """
HIJINKS BOXEE REMOTE

KCH 2013

Commands

shortcut | command - Command description.

q | quit - exit this app

REMOTE CONTROLS:
key up       | boxee up
key down     | boxee down
key left     | boxee left
key right    | boxee right
 <backspace> | boxee back
 \\ (bslash) | boxee menu
 <enter>     | boxee enter
 ` (tick)    | activate/deactivate keyboard mode

 You can also use VIM style key bindings for navigation (hjkl)

SYSTEM CONTROLS:
 1 | shutdown - Shutdown Boxee (not working)
 2 | reset    - Reset Boxee

VOLUME CONTROLS:

 u | volume up - increase volume by 2%
 d | volume down - decrease volume by 2%
 m | mute - mutes/unmutes sound

PLAYBACK CONTROLS:

 p | pause - Pauses the currently playing media.
 s | stop - Stops the currently playing media.
 n | playnext - Starts playing/showing the next media/image in the current playlist or, if currently showing a slidshow, the slideshow playlist.
 r | playprevious - Starts playing/showing the previous media/image in the current playlist or, if currently showing a slidshow, the slideshow playlist.
 > | seek forward - Seeks forward in song/media by 1%
 < | seek backwards - Seeks backwards in song/media by 1%

    """
    
    boxee = BoxeeRemote()

    stdscr = curses.initscr()
    init_colors()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(1)

    # non-blocking reads
    stdscr.timeout(0)
    pad = curses.newpad(100,100)
    stdscr.addstr(USAGE)
    stdscr.move(0,0)

    thread = RepeatEvery(1, update_curr, boxee, stdscr)
    thread.start()

    while True:
        
        command = -1
        while (command < 0):
            command = stdscr.getch()
        
        if command == ord('q'):
            thread.stop()
            kill_curses(stdscr)
            sys.exit()
        else:
            boxee.run_human_command( command )
    

if __name__ == '__main__': 
    main()

