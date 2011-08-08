#!/usr/bin/python
# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4
# GPL 2010
from __future__ import division, with_statement
import os
import urllib2
import cookielib
import json
import sqlite3
import time
import shutil
import webbrowser

from firefogg import Firefogg
import ox

import extract
import utils


__version__ = '0.1'
DEBUG = True
default_media_cache = os.environ.get('oxMEDIA', os.path.expanduser('~/.ox/media'))

def encode(filename, prefix, profile, info=None):
    if not info:
        info = utils.avinfo(filename)
    if not 'oshash' in info:
        return None
    oshash = info['oshash']
    frames = []
    cache = os.path.join(prefix, os.path.join(*utils.hash_prefix(oshash)))
    if info['video']:
        for pos in utils.video_frame_positions(info['duration']):
            frame_name = '%s.png' % pos
            frame_f = os.path.join(cache, frame_name)
            if not os.path.exists(frame_f):
                print frame_f
                extract.frame(filename, frame_f, pos)
            frames.append(frame_f)
    video_f = os.path.join(cache, profile)
    if not os.path.exists(video_f):
        print video_f
        extract.video(filename, video_f, profile, info)
    return {
        'info': info,
        'oshash': oshash,
        'frames': frames,
        'video': video_f
    }

class Client(object):
    def __init__(self, config):
        if isinstance(config, basestring):
            with open(config) as f:
                self._config = json.load(f)
        else:
            self._config = config
        self.api = API(self._config['url'], media_cache=self.media_cache())
        self.signin()

        conn, c = self._conn()

        c.execute('''CREATE TABLE IF NOT EXISTS setting (key varchar(1024) unique, value text)''')

        if int(self.get('version', 0)) < 1:
            self.set('version', 1)
            db = [
                '''CREATE TABLE IF NOT EXISTS file (
                                path varchar(1024) unique,
                                oshash varchar(16),
                                atime FLOAT,
                                ctime FLOAT,
                                mtime FLOAT,
                                size INT,
                                info TEXT,
                                created INT,
                                modified INT,
                                deleted INT)''',
                '''CREATE INDEX IF NOT EXISTS path_idx ON file (path)''',
                '''CREATE INDEX IF NOT EXISTS oshash_idx ON file (oshash)''',
            ]
            for i in db:
                c.execute(i)
            conn.commit()

    def _conn(self):
        db_conn = os.path.expanduser(self._config['cache'])
        if not os.path.exists(os.path.dirname(db_conn)):
            os.makedirs(os.path.dirname(db_conn))
        conn = sqlite3.connect(db_conn, timeout=10)
        conn.text_factory = sqlite3.OptimizedUnicode
        return conn, conn.cursor()

    def media_cache(self):
        return os.path.expanduser(self._config.get('media-cache', default_media_cache))
    
    def get(self, key, default=None):
        conn, c = self._conn()
        c.execute('SELECT value FROM setting WHERE key = ?', (key, ))
        for row in c:
            return row[0]
        return default

    def set(self, key, value):
        conn, c = self._conn()
        c.execute(u'INSERT OR REPLACE INTO setting values (?, ?)', (key, str(value)))
        conn.commit()

    def info(self, oshash):
        conn, c = self._conn()
        c.execute('SELECT info FROM file WHERE oshash = ?', (oshash, ))
        for row in c:
            return json.loads(row[2])
        return None 

    def signin(self):
        if 'username' in self._config:
            r = self.api.signin(username=self._config['username'], password=self._config['password'])
            if r['status']['code'] == 200 and not 'errors' in r['data']:
                self.user = r['data']['user']
            else:
                self.user = False
                print 'login failed'
                return False
            return True

    def scan_file(self, path):
        conn, c = self._conn()

        update = True
        modified = time.mktime(time.localtime())
        created = modified

        sql = 'SELECT atime, ctime, mtime, size, created FROM file WHERE deleted < 0 AND path=?'
        c.execute(sql, [path])
        stat = os.stat(path)
        for row in c:
            if stat.st_atime == row[0] and stat.st_ctime == row[1] and stat.st_mtime == row[2] and stat.st_size == row[3]:
                created = row[4]
                update = False
            break
        if update:
            info = utils.avinfo(path)
            if info['size'] > 0:
                oshash = info['oshash']
                deleted = -1
                t = (path, oshash, stat.st_atime, stat.st_ctime, stat.st_mtime,
                     stat.st_size, json.dumps(info), created, modified, deleted)
                c.execute(u'INSERT OR REPLACE INTO file values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', t)
                conn.commit()

    def scan(self):
        print "check for new files"
        for name in self._config['volumes']:
            path = self._config['volumes'][name]
            path = os.path.normpath(path)
            files = []
            for dirpath, dirnames, filenames in os.walk(path, followlinks=True):
                if isinstance(dirpath, str):
                    dirpath = dirpath.decode('utf-8')
                if filenames:
                    for filename in sorted(filenames):
                        if isinstance(filename, str):
                            filename = filename.decode('utf-8')
                        if not filename.startswith('._') and not filename in ('.DS_Store', ):
                            file_path = os.path.join(dirpath, filename)
                            if os.path.exists(file_path):
                                files.append(file_path)
                                self.scan_file(file_path)
            
            conn, c = self._conn()
            c.execute('SELECT path FROM file WHERE path LIKE ? AND deleted < 0', ["%s%%"%path])
            known_files = [r[0] for r in c.fetchall()]
            deleted_files = filter(lambda f: f not in files, known_files)
            if deleted_files:
                deleted = time.mktime(time.localtime())
                for f in deleted_files:
                    c.execute('UPDATE file SET deleted=? WHERE path=?', (deleted, f))
                conn.commit()

    def extract(self):
        conn, c = self._conn()

        volumes = {}
        for name in self._config['volumes']:
            path = self._config['volumes'][name]
            path = os.path.normpath(path)

            volumes[name] = {}
            volumes[name]['path'] = path
            if os.path.exists(path):
                volumes[name]['available'] = True
            else:
                volumes[name]['available'] = False

        profile = self.api.encodingProfile()['data']['profile']
        #profile = '480p.webm'
        for name in volumes:
            if volumes[name]['available']:
                prefix = volumes[name]['path']
                files = self.files(prefix)
                for f in files['files']:
                     filename = os.path.join(prefix, f['path'])
                     info = files['info'][f['oshash']]
                     if 'video' in info and \
                        info['video'] and \
                        '/extras' not in filename.lower() and \
                        '/versions' not in filename.lower():
                         print filename.encode('utf-8')
                         i = encode(filename, self.media_cache(), profile, info)

    def sync(self):
        if not self.user:
            print "you need to login"
            return
        conn, c = self._conn()

        volumes = {}
        for name in self._config['volumes']:
            path = self._config['volumes'][name]
            path = os.path.normpath(path)

            volumes[name] = {}
            volumes[name]['path'] = path
            if os.path.exists(path):
                volumes[name]['available'] = True
            else:
                volumes[name]['available'] = False

        profile = self.api.encodingProfile()['data']['profile']
        for name in volumes:
            if volumes[name]['available']:
                prefix = volumes[name]['path']
                files = self.files(prefix)
                post = {}
                post['files'] = files['files']
                post['volume'] = name
                print 'sending list of files'
                print len(json.dumps(post))
                r = self.api.update(post)
                if r['status']['code'] == 200:
                    #backend works on update request asyncronously, wait for it to finish
                    if 'taskId' in r['data']:
                        t = self.api.taskStatus(task_id=r['data']['taskId'])
                        print 'waiting for server'
                        while t['data']['status'] == 'PENDING':
                            time.sleep(5)
                            t = self.api.taskStatus(task_id=r['data']['taskId'])
                        #send empty list to get updated list of requested info/files/data
                        post = {'info': {}}
                        r = self.api.update(post)

                    if r['data']['info']:
                        info = r['data']['info']
                        max_info = 100
                        total = len(info)
                        for offset in range(0, total, max_info):
                            post = {'info': {}, 'upload': True}
                            for oshash in info[offset:offset+max_info]:
                                if oshash in files['info']:
                                    post['info'][oshash] = files['info'][oshash]
                            print 'sending info for new files', len(post['info']), offset, total
                            r = self.api.update(post)
                    
                    #send empty list to get updated list of requested info/files/data
                    post = {'info': {}}
                    r = self.api.update(post)

                    filenames = {}
                    for f in files['files']:
                        filenames[f['oshash']] = f['path']
                    
                    print 'uploading files', len(r['data']['file'])
                    if r['data']['file']:
                        for oshash in r['data']['file']:
                            if oshash in filenames:
                                filename = filenames[oshash]
                                self.api.uploadData(os.path.join(prefix, filename), oshash)

                    print 'encoding videos', len(r['data']['data'])
                    if r['data']['data']:
                        for oshash in r['data']['data']:
                            data = {}
                            if oshash in filenames:
                                filename = filenames[oshash]
                                info = files['info'][oshash]
                                if not self.api.uploadVideo(os.path.join(prefix, filename),
                                                            data, profile, info):
                                    if not self.signin():
                                        print "failed to login again"
                                        return

                            else:
                                print oshash, "missing"
                else:
                    print "updating volume", name, "failed"
                    print r

    def files(self, prefix):
        conn, c = self._conn()
        files = {}
        files['info'] = {}
        files['files'] = []
        sql = 'SELECT path, oshash, info, atime, ctime, mtime FROM file WHERE deleted < 0 AND path LIKE ? ORDER BY path'
        t = [u"%s%%"%prefix]
        c.execute(sql, t)
        for row in c:
            path = row[0]
            oshash = row[1]
            info = json.loads(row[2])
            for key in ('atime', 'ctime', 'mtime', 'path'):
                if key in info:
                    del info[key]
            files['info'][oshash] = info
            files['files'].append({
                'oshash': oshash,
                'path': path[len(prefix)+1:],
                'atime': row[3],
                'ctime': row[4],
                'mtime': row[5],
            })
        return files

    def clean(self):
        print "remove temp videos and stills"
        if os.path.exists(self.prefix()):
            shutil.rmtree(self.prefix())

class API(object):
    def __init__(self, url, cj=None, media_cache=None):
        if cj:
            self._cj = cj
        else:
            self._cj = cookielib.CookieJar()
        self._opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self._cj))
        urllib2.install_opener(self._opener)

        self.media_cache = media_cache
        if not self.media_cache:
            self.media_cache = default_media_cache 

        self.url = url
        r = self._request('api', {'docs': True})
        self._properties = r['data']['actions']
        self._actions = r['data']['actions'].keys()
        for a in r['data']['actions']:
            self._add_action(a)

    def _add_method(self, method, name):
        if name is None:
            name = method.func_name
        setattr(self.__class__, name, method)

    def _add_action(self, action):
        def method(self, *args, **kw):
            if not kw:
                if args:
                    kw = args[0]
                else:
                    kw = None
            return self._request(action, kw)
        method.__doc__ = self._properties[action]['doc']
        method.func_name = str(action)
        self._add_method(method, action)

    def _json_request(self, url, form):
        result = {}
        try:
            request = urllib2.Request(url)
            request.add_header('User-agent', 'pandora_client/%s' % __version__)
            body = str(form)
            request.add_header('Content-type', form.get_content_type())
            request.add_header('Content-length', len(body))
            request.add_data(body)
            result = urllib2.urlopen(request).read().strip()
            return json.loads(result)
        except urllib2.HTTPError, e:
            if DEBUG:
                if e.code >= 500:
                    with open('/tmp/error.html', 'w') as f:
                        f.write(e.read())
                    webbrowser.open_new_tab('/tmp/error.html')

            result = e.read()
            try:
                result = json.loads(result)
            except:
                result = {'status':{}}
            result['status']['code'] = e.code
            result['status']['text'] = str(e)
            return result
        except:
            if DEBUG:
                import traceback
                traceback.print_exc()
                if result:
                    with open('/tmp/error.html', 'w') as f:
                        f.write(str(result))
                    webbrowser.open_new_tab('/tmp/error.html')
            raise

    def _request(self, action, data=None):
        form = ox.MultiPartForm()
        form.add_field('action', action)
        if data:
            form.add_field('data', json.dumps(data))
        return self._json_request(self.url, form)

    def uploadVideo(self, filename, data, profile, info=None):
        if DEBUG:
            print filename.encode('utf-8')
        i = encode(filename, self.media_cache, profile, info)
        if not i:
            print "failed"
            return
        print i
        #upload frames
        form = ox.MultiPartForm()
        form.add_field('action', 'upload')
        form.add_field('id', str(i['oshash']))
        for key in data:
            form.add_field(str(key), data[key].encode('utf-8'))
        for frame in i['frames']:
            fname = os.path.basename(frame)
            if isinstance(fname, unicode): fname = fname.encode('utf-8')
            if os.path.exists(frame):
                form.add_file('frame', fname, open(frame, 'rb'))
        r = self._json_request(self.url, form)
        if os.path.exists(i['video']):
            #upload video in chunks
            url = self.url + 'upload/' + '?profile=' + str(profile) + '&id=' + i['oshash']
            ogg = Firefogg(cj=self._cj, debug=True)
            if not ogg.upload(url, i['video'], data):
                if DEBUG:
                    print "failed"
                return False
            else:
                if DEBUG:
                    print "done"
        else:
            if DEBUG:
                print "failed"
            return False
        return True

    def uploadData(self, filename, oshash):
        print filename
        print os.stat(filename)
        form = ox.MultiPartForm()
        form.add_field('action', 'upload')
        form.add_field('id', str(oshash))
        fname = os.path.basename(filename)
        if isinstance(fname, unicode): fname = fname.encode('utf-8')
        form.add_file('file', fname, open(filename, 'rb'))
        r = self._json_request(self.url, form)
        return r

