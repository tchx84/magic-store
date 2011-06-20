#!/usr/bin/env python

# Copyright (C) 2011, Martin Abente Lahaye
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os, posix, errno, base64

import fuse
from fuse import Fuse
fuse.fuse_python_api = (0, 2)

from xmlrpclib import ServerProxy
from ConfigParser import ConfigParser

HOSTNAME = ''
PORT     = 0
USERNAME = ''
PASSWORD = ''


_SUGAR_METADATA = '/.Sugar-Metadata'

_ATTR = -1
_DIR = -2
_CACHE = {}

def _set_cache(_type, path, value):
    if path not in _CACHE:
        _CACHE[path] = {}
    _CACHE[path][_type] = value

def _get_cache(_type, path):
    if path not in _CACHE or \
        _type not in _CACHE[path]:
            return None
    return _CACHE[path][_type]

def _flush_cache(path):
    del _CACHE[path]

class MagicStoreFS(Fuse):

    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)
        uri = 'http://%s:%d' % (HOSTNAME, PORT)
        self._server = ServerProxy(uri)

    def _request(self, method, *params):
        return method(USERNAME, PASSWORD, *params)

    def fsinit(self):
        print 'fsinit'
        pass

    def readdir(self, path, offset):
        print 'readdir %s' % path
        directory = _get_cache(_DIR, path)
        if directory is None:
            directory = self._request(self._server.remote_readdir, path, offset)
            _set_cache(_DIR, path, directory)
        for entry in directory:
            yield fuse.Direntry(entry)

    def getattr(self, path):
        print 'getattr %s' % path
        stats = _get_cache(_ATTR, path)
        if stats is None:
            stats = self._request(self._server.remote_getattr, path)
            _set_cache(_ATTR, path, stats)
        if stats is -1:
            return -errno.ENOENT
        return posix.stat_result(stats)

    def rename(self, original_path, renamed_path):
        print 'rename %s to %s' % (original_path, renamed_path) 
        result, original_directory, renamed_directory, attr = self._request(
            self._server.remote_rename, original_path, renamed_path)
        _flush_cache(original_path)
        self._update_directory(original_path, original_directory)
        self._update_directory(renamed_path, renamed_directory)
        _set_cache(_ATTR, renamed_path, attr)

    def statfs(self):
        print 'statfs'
        stats = self._request(self._server.remote_statfs)
        return posix.statvfs_result(stats)

    def read(self, path, length, offset):
        print 'read %s %d %d' % (path, length, offset)
        content = _get_cache(offset, path)
        if content is None:
            content = self._request(self._server.remote_read, path, length, offset)
            content = base64.decodestring(content)
        if path.startswith(_SUGAR_METADATA):
            _set_cache(offset, path, content)
        return content

    def write(self, path, content, offset):
        print 'write %s %d %d' % (path, len(content), offset)
        if path.startswith(_SUGAR_METADATA):
            _set_cache(offset, path, content)
        content = base64.encodestring(content)
        result, attr = self._request(self._server.remote_write, path, content, offset)
        if result is -1:
            raise IOError
        _set_cache(_ATTR, path, attr)
        return result

    def release(self, path, fh=0):
        print 'release %s %s' % (path, str(fh))
        return 0

    def flush(self, path, fh=0):
        print 'flush %s %s' % (path, str(fh))
        return 0

    def fsync(self, path, fdatasync, fh=0):
        print 'fsync %s %s %s' % (path, str(fdatasync), str(fh))
        return 0

    def chmod(self, path, mode):
        print 'chmod %s %s' % (path, str(mode))
        resilt, attr = self._request(self._server.remote_chmod, path, mode)
        _set_cache(_ATTR, path, attr)

    def fgetattr(self, path, fh=0):
        print 'fgetattr %s %s' % (path, str(fh))
        stats = _get_cache(_ATTR, path)
        if stats is None:
            stats = self._request(self._server.remote_fgetattr, path, fh)
            _set_cache(_ATTR, path, stats)
        if stats is -1:
            return -errno.ENOENT
        return posix.stat_result(stats)

    def _update_directory(self, path, directories):
        path_dir = os.path.dirname(path)
        print 'saving in %s : %s' % (path_dir, str(directories))
        _set_cache(_DIR, path_dir, directories)

    def create(self, path, flags, mode):
        print 'create %s %s %s' % (path, str(flags), str(mode))
        result, directory, attr  = self._request(
            self._server.remote_create, path, flags, mode)
        self._update_directory(path, directory)
        _set_cache(_ATTR, path, attr)

    def unlink(self, path):
        print 'unlink %s' % path
        result, directory  = self._request(self._server.remote_unlink, path)
        self._update_directory(path, directory)
        _flush_cache(path)
        return result

    def mkdir(self, path, mode):
        print 'mkdir %s %s' % (path, str(mode))
        result, directory, attr = self._request(self._server.remote_mkdir, path, mode)
        self._update_directory(path, directory)
        _set_cache(_ATTR, path, attr)
        return result
 
    def rmdir(self, path):
        print 'rmdir %s' % path
        result, directory = self._request(self._server.remote_rmdir, path)
        self._update_directory(path, directory)
        _flush_cache(path)
        return result

def _load_config():
    global HOSTNAME, PORT, USERNAME, PASSWORD
    script_path = os.path.abspath( __file__ )
    client_path = os.path.dirname(script_path)

    config_path = os.path.join(client_path, 'client.config')
    if not os.path.exists(config_path):
        print 'Failed to start! Can\'t find \'client.config\' file'
        exit(-1)
    config = ConfigParser()
    config.read(config_path)

    HOSTNAME = config.get('client', 'hostname', 'localhost')
    print 'HOSTNAME %s' % HOSTNAME
    PORT = int(config.get('client', 'port', 8080))
    print 'PORT %s' % PORT

    USERNAME = config.get('user', 'username', '').upper()
    print 'USERNAME %s' % USERNAME
    PASSWORD = config.get('user', 'password', '')
    print 'PASSWORD %s' % PASSWORD

def main():
    usage = """
Magic Store File System
 
""" + Fuse.fusage
 
    _load_config()
    fs = MagicStoreFS(version = '%prog' + fuse.__version__,
                usage = usage,
                dash_s_do='setsingle')
    fs.parse(errex = 1)
    fs.main()
 
if __name__ == '__main__':
    main()
