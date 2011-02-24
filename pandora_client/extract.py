#!/usr/bin/python
# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4
# GPL 2010
from __future__ import division, with_statement

import fractions
from glob import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import shutil
import tempfile
import time

import ox

from utils import avinfo, AspectRatio, run_command


def frame(video, target, position):
    fdir = os.path.dirname(target)
    if fdir and not os.path.exists(fdir):
        os.makedirs(fdir)

    '''
    #oxframe
    cmd = ['oxframe', '-i', video, '-p', str(position), '-o', target]
    print cmd
    r = run_command(cmd)
    return r == 0
    '''

    #mplayer
    cwd = os.getcwd()
    target = os.path.abspath(target)
    framedir = tempfile.mkdtemp()
    os.chdir(framedir)
    cmd = ['mplayer', '-noautosub', video, '-ss', str(position), '-frames', '2', '-vo', 'png:z=9', '-ao', 'null']
    print cmd
    r = run_command(cmd)
    images = glob('%s/*.png' % framedir)
    if images:
        shutil.move(images[-1], target)
        r = 0
    else:
        r = 1
    os.chdir(cwd)
    shutil.rmtree(framedir)
    return r == 0

def video(video, target, profile, info):
    if not os.path.exists(target):
        fdir = os.path.dirname(target)
        if not os.path.exists(fdir):
            os.makedirs(fdir)

    if info['video']:
        dar = AspectRatio(info['video'][0]['display_aspect_ratio'])

    '''
        look into
            lag
            mb_static_threshold
            qmax/qmin
            rc_buf_aggressivity=0.95
            token_partitions=4
            level / speedlevel
            bt?
    '''
    profile, format = profile.split('.')

    if profile == '720p':
        height = 720

        audiorate = 48000
        audioquality = 5
        audiobitrate = None
        audiochannels = None
    if profile == '480p':
        height = 480

        audiorate = 44100
        audioquality = 3
        audiobitrate = None
        audiochannels = 2
    elif profile == '360p':
        height = 360

        audiorate = 44100
        audioquality = 1
        audiobitrate = None
        audiochannels = 1
    elif profile == '240p':
        height = 240

        audiorate = 44100
        audioquality = 0
        audiobitrate = None
        audiochannels = 1
    else:
        height = 96

        audiorate = 22050
        audioquality = -1
        audiobitrate = '22k'
        audiochannels = 1

    bpp = 0.17
    if info['video']:
        fps = AspectRatio(info['video'][0]['framerate'])

        width = int(dar * height)
        width += width % 2 

        bitrate = height*width*fps*bpp/1000
        aspect = dar.ratio
        #use 1:1 pixel aspect ratio if dar is close to that
        if abs(width/height - dar) < 0.02:
            aspect = '%s:%s' % (width, height)

        video_settings = [
            '-vb', '%dk'%bitrate, '-g', '%d' % int(fps*2),
            '-s', '%dx%d'%(width, height),
            '-aspect', aspect,
            '-vf', 'yadif',
        ]
    else:
        video_settings = ['-vn']

    if info['audio']:
        audio_settings = ['-ar', str(audiorate), '-aq', str(audioquality)]
        if audiochannels and 'channels' in info['audio'][0] and info['audio'][0]['channels'] > audiochannels:
            audio_settings += ['-ac', str(audiochannels)]
        if audiobitrate:
            audio_settings += ['-ab', audiobitrate]
        audio_settings +=['-acodec', 'libvorbis']
    else:
        audio_settings = ['-an']

    cmd = ['ffmpeg', '-y', '-i', video] \
          + audio_settings \
          + video_settings \
          + ['-f','webm', target]
    print cmd

    #r = run_command(cmd, -1)
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    '''
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    line = p.stderr.readline()
    while line:
        if line.startswith('frame='):
            frames = line.split('=')[1].strip().split(' ')[0]
        line = p.stderr.readline()
    '''
    try:
        p.wait()
        r = p.returncode
    except KeyboardInterrupt:
        r = 1
        print "\ncleaning up unfinished encoding:\nremoving", target
        print "\n"
        os.unlink(target)
        sys.exit(1)

    print "done"
    return r == 0

