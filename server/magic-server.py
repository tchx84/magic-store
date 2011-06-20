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

import os, base64
from ConfigParser import ConfigParser
from SimpleXMLRPCServer import SimpleXMLRPCServer

HOSTNAME     = ''
PORT         = 0
MAGIC_ROOT   = ''
MAX_QUOTA    = 0
MAX_FILESIZE = 0
USERS        = {}

METHOD_STATS = {}

def _set_method_stat(method):
    global METHOD_STATS
    if method not in METHOD_STATS:
        METHOD_STATS[method] = 1
    else:
        METHOD_STATS[method] = METHOD_STATS[method] + 1 

def _print_method_stats():
    global METHOD_STATS
    for method in METHOD_STATS:
        print '%s: %d' % (method, METHOD_STATS[method])
    print ''

class MagicStore(object):

    def __init__(self, target_root):
        if not os.path.exists(target_root):
            os.mkdir(target_root)
        self._target_root = target_root
        print 'MagicStore.__init__ %s' % self._target_root

    def _get_root_size(self):
        target_root_size = 0
        for dirpath, dirnames, filenames in os.walk(self._target_root):
            for filename in filenames:
                filename_path = os.path.join(dirpath, filename)
                target_root_size += os.path.getsize(filename_path)
        return target_root_size

    def _fit_quota(self, content_size):
        root_size = self._get_root_size()
        return (root_size + content_size) < MAX_QUOTA

    def _secure_path(self, target_path):
        print '_get_path %s' % target_path
        if target_path.startswith('/'):
             target_path = target_path[1:]
        secure_path = os.path.join(self._target_root, target_path)
        print '_get_path %s' % secure_path
        if not secure_path.startswith(MAGIC_ROOT):
            raise ValueError
        return secure_path

    def _readdir(self, target_path, offset):
        print '_readdir %s %s' % (target_path, str(offset))
        directory = []
        for entry in os.listdir(target_path):
            directory.append(entry)
        return directory

    def remote_readdir(self, target_path, offset):
        print 'remote_readdir %s' % target_path
        target_path = self._secure_path(target_path)
        return self._readdir(target_path, offset)

    def _getattr(self, target_path):
        print '_getattr %s' % target_path
        try:
            stats = os.lstat(target_path)[:]
        except:
            stats = -1
        return stats

    def remote_getattr(self, target_path):
        print 'remote_getattr %s' % target_path
        target_path = self._secure_path(target_path)
        return self._getattr(target_path)

    def remote_rename(self, original_path, renamed_path):
        original_path = self._secure_path(original_path)
        renamed_path = self._secure_path(renamed_path)
        print 'remote_rename %s to %s' % (original_path, renamed_path)
        os.rename(original_path, renamed_path)
        original_directory = self._directory_update(original_path)
        renamed_directory =  self._directory_update(renamed_path)
        attr = self._getattr(renamed_path)
        return (0, original_directory, renamed_directory, attr)

    def remote_statfs(self):
        global MAX_QUOTA
        print 'remote_statfs %s' % self._target_root
        try:
            statvfs = os.statvfs(self._target_root)
            f_bsize = statvfs.f_bsize
            f_blocks = MAX_QUOTA/f_bsize
            root_size = self._get_root_size()
            f_bavail = (MAX_QUOTA - root_size)/f_bsize
            stats = (f_bsize, 0, f_blocks, 0, f_bavail, 0, 0, 0, 0, 0)
        except:
            stats = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        print 'remote_statfs %s' % str(stats)
        return stats

    def remote_read(self, target_path, length, offset):
        target_path = self._secure_path(target_path)
        print 'remote_read %s %s %s' % (target_path, str(length), str(offset))
        try:
            _file = open(target_path, 'r')
            _file.seek(offset)
            content = _file.read(length)
            content = base64.encodestring(content)
        except:
            content = ''
        return content

    def remote_write(self, target_path, content, offset):
        target_path = self._secure_path(target_path)
        content = base64.decodestring(content)
        content_size = len(content)
        print 'remote_write %s %d %d' % (target_path, content_size, offset)

        # TODO laugh many times about this
        if offset > MAX_FILESIZE or \
            not self._fit_quota(content_size):
                raise IOError
        try:
            _file = open(target_path, 'r+')
            _file.seek(offset)
            _file.write(content)
            _file.close()
            attr = self._getattr(target_path)
        except:
            content_size = -1
            attr = -1
        return (content_size, attr)

    def remote_chmod(self, target_path, mode):
        target_path = self._secure_path(target_path)
        print 'remote_chmod %s %s' % (target_path, str(mode))
        os.chmod(target_path, mode)
        attr = self._getattr(target_path)
        return (0, attr)

    def _fgetattr(self, target_path, fh=0):
        print '_fgetattr %s %s' % (target_path, str(fh))
        try:
            _file = open(target_path, 'r')
            stats = os.fstat(_file.fileno())[:]
        except:
            stats = -1
        return stats

    def remote_fgetattr(self, target_path, fh=0):
        print 'remote_fgetattr %s %s' % (target_path, str(fh))
        target_path = self._secure_path(target_path)
        return self._fgetattr(target_path, fh)

    def _directory_update(self, target_path):
        target_dir = os.path.dirname(target_path)
        print '_directory_update %s' % target_dir
        return self._readdir(target_dir, None)

    def remote_create(self, target_path, flags, mode):
        target_path = self._secure_path(target_path)
        print 'remote_create %s %s %s' % (target_path, str(flags), str(mode))
        _file = open(target_path, 'w')
        _file.close()
        directory = self._directory_update(target_path)
        attr = self._getattr(target_path)
        return (0, directory, attr)

    def remote_unlink(self, target_path):
        target_path = self._secure_path(target_path)
        print 'remote_unlink %s' % target_path
        os.unlink(target_path)
        directory = self._directory_update(target_path)
        return (0, directory)

    def remote_mkdir(self, target_path, mode):
        target_path = self._secure_path(target_path)
        print 'remote_mkdir %s %s' % (target_path, str(mode))
        os.mkdir(target_path, mode)
        directory = self._directory_update(target_path)
        attr = self._getattr(target_path)
        return (0, directory, attr)

    def remote_rmdir(self, target_path):
        target_path = self._secure_path(target_path)
        print 'remote_rmdir %s' % target_path
        os.rmdir(target_path)
        directory = self._directory_update(target_path)
        return (0, directory)


class MagicStoreServer(SimpleXMLRPCServer):

    def _dispatch(self, method, params):
        print '_dispatch method %s params %s' % (method, str(params))
        self._do_authenticate(params)
        return self._do_method(method, params)      

    def _do_authenticate(self, params):
        global USERS
        username, password = params[:2]
        if username not in USERS or \
            password != USERS.get(username, None):
                print '_do_authentication %s rejected' % str(username)
                raise ValueError

    def _do_method(self, method, params):
        if not method.startswith('remote_'):
            print '_do_method %s not valid' % method
            raise AttributeError

        username = params[0]
        target_root = os.path.join(MAGIC_ROOT, username)
        user_instance = MagicStore(target_root)
        instance_method = getattr(user_instance, method)    
        method_params = params[2:]
        result = instance_method(*method_params)
        if result is None:
            print '_do_method WATCHOUT! %s' % method
        print '_do_method %s' % str(result)

        _set_method_stat(method)
        _print_method_stats()

        return result


def _load_config():
    global HOSTNAME, PORT, MAGIC_ROOT, MAX_QUOTA, MAX_FILESIZE, USERS
    script_path = os.path.abspath( __file__ )
    server_path = os.path.dirname(script_path)

    config_path = os.path.join(server_path, 'server.config')
    if not os.path.exists(config_path):
        print 'Failed to start! can\'t find \'server.config\' file'
        exit(-1)

    config = ConfigParser()
    config.read(config_path)
     
    HOSTNAME = config.get('server', 'hostname', 'localhost')
    print '_load_config HOSTNAME %s' % HOSTNAME
    PORT = int(config.get('server', 'port', 8080))
    print '_load_config PORT %d' % PORT

    default_root = os.path.join(server_path, 'root')
    MAGIC_ROOT = config.get('magic_store', 'magic_root', default_root)
    print '_load_config MAGIC_ROOT %s' % MAGIC_ROOT 
    MAX_QUOTA = int(config.get('magic_store', 'max_quota', 2097152))
    print '_load_config MAX_QUOTA %d' % MAX_QUOTA
    MAX_FILESIZE = int(config.get('magic_store', 'max_filesize', 5242880))
    print '_load_config MAX_FILESIZE %d' % MAX_FILESIZE

    for user_data in config.items('users'):
        username, password = user_data[0].upper(), user_data[1]
        USERS[username] = password
        print '_load_config username %s password %s' % (username, password)

def main():
    _load_config()
    server = MagicStoreServer((HOSTNAME, PORT))
    server.serve_forever()
 
if __name__ == '__main__':
    main()
