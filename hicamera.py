#!/usr/bin/python
import io
import sys
import os
import logging
import argparse
import subprocess
import socket
import time
import json
import picamera
import picamera.array
from datetime import datetime
import numpy as np
from tornado import web, httpserver, ioloop, gen, websocket, iostream
#from base64 import b64encode
from threading import Lock
import shlex


class MotionHandler(object):
    def motion_event(self, value):
        pass


class FileOutputStream(object):
    def __init__(self, fp):
        self.fp = fp
        self.lock = Lock()

    def write(self, data):
        with self.lock:
            self.fp.write(data)
        return len(data)

    @property
    def closed(self):
        return self.fp.closed
   
    def close(self):
        with self.lock:
            self.fp.close()


class ProcessOutputStream(object):
    def __init__(self, command, output=None):
        logging.debug("spawn process %s", " ".join(command))
        self.process = subprocess.Popen( command, 
            stdin=subprocess.PIPE, stdout=io.open(os.devnull, 'wb') if output is None else output, stderr=subprocess.STDOUT,
            shell=False, close_fds=True            
        )
        self.lock = Lock()
        self.ioloop = ioloop.IOLoop.current()
        self.ioloop.add_callback(self.check_closed)
        pass
    
    def write(self, b):
        if not self.closed:
            with self.lock:
                self.process.stdin.write(b)
        pass

    def close(self):
        try:
            if not self.closed:
                logging.debug('close spawned process')
                with self.lock:
                    self.process.stdin.close()
        except:
            logging.exception('error while close spawned process')
            pass

    @property
    def closed(self):
        return self.process.poll() is not None

    def check_closed(self):
        if not self.closed:
            self.ioloop.add_timeout(1000, self.check_closed)
        pass


class MJPEGStreamBuffer(object):
    def __init__(self, request_handler, boundary="MJPEGFRAME"):
        self.request_handler = request_handler
        self.boundary = boundary
        self.buffer = io.BytesIO()
        self.ioloop = ioloop.IOLoop.current()

    def write(self, b):
        if b.startswith(b'\xff\xd8'):
            size = self.buffer.tell()
            if size > 0:
                frame = self.buffer.getvalue()

                self.buffer.seek(0)
                self.buffer.truncate()
                #self.ioloop.add_callback(self.write_frame, frame)
                self.write_frame(frame)

        return self.buffer.write(b)
    
    def closed(self):
        return self.request_handler.request.connection.stream.closed()

    #@gen.coroutine
    def write_frame(self, frame):
        try:
            header = '\r\n'.join(
                [ '--%s' % self.boundary, 'Content-Type: image/jpeg', 'Content-Length: %d' % len(frame), '', '']
            )

            self.request_handler.write(header)
            self.request_handler.write(frame)
            self.request_handler.flush()
        except:
            logging.exception('write_frame error')
        pass


class VideoBuffer(object):
    def __init__(self, camera, pre_seconds):
        self.camera = camera
        self.ioloop = ioloop.IOLoop.current()
        self.circular = picamera.PiCameraCircularIO(self.camera, size=1*1024*1024)
        self.out_fd = []
        self.write_to_circular = False
        pass

    def write(self, b):
        try:
            if True or self.write_to_circular:
                #self.ioloop.add_callback(self.circular.write, b)
                self.circular.write(b)

            for stream in list(self.out_fd):
                if stream.closed:
                    self.out_fd.remove(stream)
                else:
                    #self.ioloop.add_callback(self.write_to_stream, stream, b)
                    stream.write(b)
        except:
            logging.exception('VideoBuffer exception')
        pass

    def copy_circular(self, output, seconds):
        buffer = self.circular

        with buffer.lock:
            save_pos = buffer.tell()
            try:
                # find position of SPS frame at least last N seconds
                pos = None
                last = None
                curr = None

                seconds = int(seconds * 1000000)
                for frame in reversed(buffer.frames):
                    if frame.timestamp is not None:
                        curr = frame.timestamp

                        if last is None:
                            last = frame.timestamp

                    if frame.frame_type == 2 and last is not None:
                        pos = frame.position
                        if last - curr >= seconds:
                            break

                logging.debug('found %d secs in curcular buffer (size: %d)', (last-curr)/1000000, save_pos-pos)
                # write to output stream from finded position
                if pos is not None:
                    buffer.seek(pos)
                    while True:
                        buf = buffer.read1()
                        if not buf:
                            break
                        #yield output.write(buf)
                        output.write(buf)
            finally:
                buffer.seek(save_pos)
            pass
        pass

    def write_to_stream(self, stream, b):
        if not stream.closed():
            stream.write(b)
        pass

    def flush(self):
        pass

    def attach_stream(self, stream):
        self.out_fd.append(stream)

    def remove_stream(self, stream):
        if stream in self.out_fd:
            self.out_fd.remove(stream)


class MotionDetector(picamera.array.PiMotionAnalysis):
    def __init__(self, camera, handler):
        """
        
        :type camera: picamera.PiCamera
        :type handler: MotionHandler
        """
        super(MotionDetector, self).__init__(camera)
        self.handler = handler
        self.motion_treshold_value = 0
        self.motion_treshold_count = 5
        self.motion_treshold_sad = 300
        self.motion_frames = 3
        self.motion_cnt = 0

    def analyse(self, a):
        try:
            b = (
                np.square(a['x'].astype(np.uint16)) +
                np.square(a['y'].astype(np.uint16))
            ).astype(np.uint16)

            b = np.logical_and(
                (b > self.motion_treshold_value) , (a['sad'] < self.motion_treshold_sad)
            )
            n = b.sum()
            if n > self.handler.motion_factor:
                self.handler.motion_factor = n

            if n > self.motion_treshold_count:
                self.motion_cnt = self.motion_cnt + 1
            else:
                self.motion_cnt = 0

            if self.motion_cnt >= self.motion_frames:
                self.handler.motion_event(n)
        except:
            logging.exception('motion detection error')
        pass


class Recorder(MotionHandler):
    def __init__(self, camera, params):
        self.params = params
        self.camera = camera
        self.record_flag = False
        self.motion_detector = MotionDetector(camera, self)
        self.motion_factor = 0
        self.video_buffer = VideoBuffer(self.camera, self.params.buffer)
        self.last_motion = time.time()
        self.ioloop = ioloop.IOLoop.current()
        self.motion_timeout = None
        self.snapshot = io.BytesIO()
        self.snapshot_time = time.time()*1000

    def start_process(self, command_line, debug=False):
        output = "%s.log" % self.params.timestamp if debug else None
        cmd = command_line.format(**vars(self.params))
        return ProcessOutputStream(shlex.split(cmd), output)
        pass

    def motion_event(self, value):
        now = time.time()
        if now - self.last_motion > self.params.event_gap:
            logging.info('motion event started (factor %d)', value)
            try:
                self.start_record()

                # send snapshot on first motion frame to process 
                process = self.start_process(self.params.on_motion_begin)
                buffer = self.take_snapshot()
                process.write(buffer.getvalue())
                process.close()
            except:
                logging.exception('start motion error')

        if self.motion_timeout is not None:
            self.ioloop.remove_timeout(self.motion_timeout)

        self.motion_timeout = self.ioloop.call_later(self.params.event_gap, self.end_motion)
        self.last_motion = now
        pass

    def end_motion(self):
        logging.info('motion event finished')
        try:
           self.stop_record()

           process = self.start_process(self.params.on_motion_end)
           process.close()
        except:
           logging.exception('end motion error')
        pass

    def take_snapshot(self, expire=0):
        now = time.time()*1000
        if now-self.snapshot_time >= expire:
            self.snapshot_time = now

            self.snapshot.seek(0)
            self.snapshot.truncate()
            self.camera.capture(self.snapshot, format='jpeg', use_video_port=True)
        return self.snapshot

    def start_record(self):
        if self.record_flag:
            return
        self.record_flag = True

        self.params.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        logging.info('start recording')

        self.record_stream = FileOutputStream(open(self.params.motion_file.format(**vars(self.params)), 'wb'))
        self.video_buffer.attach_stream(self.record_stream)

        buffer_stream = open(self.params.pre_motion_file.format(**vars(self.params)), 'wb')
        self.video_buffer.copy_circular(buffer_stream, self.params.buffer)
        buffer_stream.close()
        pass

    def stop_record(self):
        if not self.record_flag:
            return
        logging.info('stop recording')

        self.video_buffer.remove_stream(self.record_stream)
        self.record_stream.close()

        post_process_cmd = self.params.post_process.format(**vars(self.params))
        if post_process_cmd != '':
            logging.debug('start post process command: %s', post_process_cmd)
            subprocess.Popen(post_process_cmd, shell=True, stdout=io.open(os.devnull, 'wb'), stderr=subprocess.STDOUT)
        self.record_flag = False
        pass

    def time_marker(self):
        now = datetime.now()

        #motion_mark = 'M' if now - self.last_motion < self.params.event_gap else ' '
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        self.camera.annotate_text = "%s.%01d" % (now_str, int(now.microsecond/100000)) #+ "\n[%d %s]" % (self.motion_factor, motion_mark)
        self.motion_factor = 0

    def start(self):
        self.marker_callback = ioloop.PeriodicCallback(self.time_marker, callback_time=100)
        self.camera.start_recording(
            self.video_buffer,
            format='h264',
            #format='mjpeg',
            inline_headers=True,
            motion_output=self.motion_detector
        )
        self.marker_callback.start()
        pass


class SnapshotHandler(web.RequestHandler):
    def initialize(self, recorder):
        self.recorder = recorder
    
    @gen.coroutine
    def get(self):
        self.set_header('Content-Type', 'image/jpeg')

        buffer = self.recorder.take_snapshot()
        yield self.write(buffer.getvalue())
        pass


class StreamHandler(web.RequestHandler):
    def initialize(self, recorder):
        self.recorder = recorder
        self.boundary = 'MJPEGFRAME'

    @web.asynchronous
    def get(self):
        self.set_header('Content-Type', 'multipart/x-mixed-replace;boundary=%s' % self.boundary)
        self.flush()
        try:
            self.rate = int(self.get_argument('rate', '1000'))
            logging.info('start streaming with rate %d', self.rate)

            self.task = ioloop.PeriodicCallback(self.write_frame, self.rate)
            self.write_frame()
            self.task.start()
            logging.info('streaming finished')
        except:
            logging.exception('streaming error')
            self.finish()
        pass

    def on_connection_close(self):
        self.task.stop()
        pass

    def write_frame(self):
        try:
            frame = self.recorder.take_snapshot(self.rate/2).getvalue()
            header = '\r\n'.join(
                [ '--%s' % self.boundary, 'Content-Type: image/jpeg', 'Content-Length: %d' % len(frame), '', '']
            )
            self.write(header)
            self.write(frame)
            self.flush()
        except:
            logging.exception('write_frame error')
            self.finish()
        pass


class WSStreamHandler(websocket.WebSocketHandler):
    def initialize(self, recorder):
        self.recorder = recorder
        self.task = None

    def check_origin(self, origin):
        return True

    def on_close(self):
        self.stop_stream()
        pass

    def on_message(self, message):
        try:
            command = json.loads(message)
            logging.debug('got command %s', message)
            if command['cmd'] == 'start':
                rate = command.get('rate', 1000)
                self.start_stream(rate)

            if command['cmd'] == 'stop':
                self.stop_stream()
        except:
            logging.exception('on_message error')
        pass

    def stop_stream(self):
        if self.task is not None:
            logging.info('stop streaming')
            self.task.stop()
            self.task = None

    def start_stream(self, rate):
        self.stop_stream()

        self.rate = rate
        logging.info('start streaming with rate %d', self.rate)
        self.write_frame()

        self.task = ioloop.PeriodicCallback(self.write_frame, self.rate)
        ioloop.IOLoop.current().add_callback(self.task.start)
        pass

    def write_frame(self):
        try:
            frame = self.recorder.take_snapshot(self.rate/2).getvalue()
            self.write_message(frame, True)
        except:
            self.task.stop()
        pass


class ControlHandler(web.RequestHandler):
    def initialize(self, recorder):
        self.recorder = recorder

    def get(self, context, action):
        if context == 'record':
            if action == 'start':
                self.recorder.start_record()
            elif action == 'stop':
                self.recorder.stop_record()

        if context == 'motion':        
            if action == 'start':
                self.recorder.motion_event(0)
            elif action == 'stop':
                self.recorder.end_motion()
        pass


class BufferHandler(web.RequestHandler):
    def initialize(self, recorder):
        self.recorder = recorder

    def get(self):
        seconds = int(self.get_argument('sec', '3'))
        logging.info("get last %d seconds", seconds)
        self.set_header('Content-Type', 'video/mp4')

        buffer = self.recorder.video_buffer
        buffer.copy_circular(self, seconds)
        self.flush() 
        pass


def main():
    class LoadFromFile(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            with values as f:
                parser.parse_args(f.read().split(), namespace)

    parser = argparse.ArgumentParser(fromfile_prefix_chars='@')

    parser.add_argument("-c", "--config", type=open,
                        action=LoadFromFile,
                        help="Load config from file")
    parser.add_argument("-v", action="store_true", default=False, help="Verbose logging", dest="verbose")
    parser.add_argument("-p", '--buffer', type=int, default=3)
    parser.add_argument("--width",   type=int, default=1296)
    parser.add_argument("--height", type=int, default=972)
    parser.add_argument("--rot", "-r", type=int, default=0)
    parser.add_argument("--bright", "-b", type=int, default=50)
    parser.add_argument("--fps", "-f", type=int, default=30)
    parser.add_argument("--gap", "-g", type=int, default=5, dest="event_gap")
    parser.add_argument("--listen", type=int, default=8092)

    parser.add_argument("--pre-motion-file", default="storage/{timestamp}_pre.h264")
    parser.add_argument("--motion-file", default="storage/{timestamp}_mov.h264")
    parser.add_argument("--post-process", default="")

    parser.add_argument("--on-motion-begin", default="")
    parser.add_argument("--on-motion-end", default="")

    parser.add_argument("--logfile", help="Logging into file")

    params = parser.parse_args()

    # configure logging
    logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                        level=logging.DEBUG if params.verbose else logging.INFO,
                        filename=params.logfile)

    camera = picamera.PiCamera(
        resolution=(params.width, params.height),
        framerate=params.fps
    )
    camera.rotation = params.rot
    camera.brightness = params.bright

    recorder = Recorder(camera, params)
    recorder.start()

    arguments = {"recorder": recorder}

    webapp = web.Application([
        (r"/camera/snapshot",            SnapshotHandler, arguments),
        (r"/camera/stream",              StreamHandler,   arguments),
        (r"/camera/stream/ws",           WSStreamHandler, arguments),
        (r"/camera/buffer",              BufferHandler, arguments),
        (r"/camera/(record|motion)/(start|stop)", ControlHandler, arguments),
    ])
    server = httpserver.HTTPServer(webapp, xheaders=True)
    server.listen(params.listen)

    logging.info("started camera recorder")
    logging.info("listen on port %d", params.listen)

    # Main loop start
    ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    main()
