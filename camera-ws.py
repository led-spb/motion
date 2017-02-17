#!/usr/bin/python
import logging
from tornado import websocket, web, ioloop, iostream
import urlparse
import socket, json


class AsyncStreamHttp:
   def __init__( self, url, on_data=None, on_close=None, on_headers=None ):
       self.url = url
       self.url_data = urlparse.urlparse(url)

       self.on_data    = on_data
       self.on_close   = on_close
       self.on_headers = on_headers
       self.headers  = []

       self.stream = iostream.IOStream( socket.socket( socket.AF_INET, socket.SOCK_STREAM, 0) )
       self.stream.set_close_callback( self._closed )
       self.stream.set_nodelay(1)
       self.stream.connect( (self.url_data.hostname, 80 if self.url_data.port is None else self.url_data.port), self._connected )

   def _connected(self):
       buffer = "%s %s HTTP/1.1\r\nHost: %s\r\n\r\n" % ( "GET", "/" if self.url_data.path==None else self.url_data.path , self.url_data.hostname )
       # write request and read response headers
       self.stream.read_until("\r\n\r\n", self._on_headers)
       self.stream.write( buffer )

   def _on_headers(self, data):
       data = data.split("\r\n")
       self.status  = data[0]
       self.headers = data[1:]

       if self.on_headers!=None:
          self.on_headers( self.status, self.headers )
       # start reading stream
       self._read_data()

   def _on_data(self,data):
       if self.on_data!=None:
          self.on_data(data)
       self._read_data()
       pass

   def _read_data(self):
       self.stream.read_until_close( streaming_callback=self.on_data )
       #self.stream.read_bytes( 8192, callback=self._on_data )

   def _closed(self):
       if self.on_close!=None:
          self.on_close()
       pass

   def _dummy(self,data):
       pass

   def close(self):
       try:
          self.stream.close()
       except:
          pass
       pass





class SocketHandler(websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def on_message(self, message):
        pass

    def open(self, *args):
        logging.info( "client connected" )
        self.mjpeg = ''
        self.http = AsyncStreamHttp( "http://localhost:8081/", self.on_http_data )

    def on_http_data(self, data):
        try:
          self.mjpeg += data
          a = self.mjpeg.find("\xff\xd8")
          b = self.mjpeg.find("\xff\xd9")
          if a!=-1 and b!=-1:
             jpg = self.mjpeg[a:b+2]
             self.mjpeg = self.mjpeg[b+2:]
             self.write_message( jpg, True )
        except:
          self.close()
        pass

    def on_close(self):
        logging.info( "client disconnected code:%d, reason:%s" % (-1 if self.close_code is None else self.close_code, "None" if self.close_reason is None else self.close_reason) )
        self.http.close()
        pass


app = web.Application([
    (r'/camera', SocketHandler ),
])

if __name__ == '__main__':
    import tornado.options
    tornado.options.parse_command_line()

    app.listen(9002)
    ioloop.IOLoop.instance().start()