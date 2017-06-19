from rapidlib.requests import get, HttpResponseHandle
from untwisted.network import xmap, core

def on_done(con, response):
    print response.headers
    print response.code
    print response.version
    print response.reason 
    print response.fd.read()

if __name__ == '__main__':
    con = get('https://api.github.com', '/user', 
    ssl=True, auth=('iogf', 'godhelpsme'))

    xmap(con, HttpResponseHandle.HTTP_RESPONSE, on_done)
    core.gear.mainloop()







