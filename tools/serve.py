import http.server, os, functools
class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = super().translate_path(path)
        if not os.path.exists(p) and os.path.exists(p + '.html'): return p + '.html'
        return p
    def log_message(self,*a): pass
http.server.ThreadingHTTPServer(('',8765), functools.partial(H, directory='/home/claude/site')).serve_forever()
