"""

"""

from rapidserv import RapidServ, make, RequestHandle
import shelve

DB_FILENAME = 'DB'
DB          = shelve.open(make(__file__, DB_FILENAME))
RequestHandle.MAX_SIZE = 1024 * 1024 * 3
app    = RapidServ(__file__)

@app.overflow
def response(con, request):
    con.set_response('HTTP/1.1 400 Bad request')
    HTML = '<html> <body> <h1> Bad request </h1> </body> </html>'
    con.add_data(HTML)
    con.done()

@app.request('GET /')
def index(con, request):
    con.render('view.jinja', posts = DB.keys())
    con.done()

@app.request('GET /load_index')
def load_index(con, request):
    con.add_data(DB[request.query['index'][0]], 
    mimetype='image/jpeg;')

    con.done()

@app.request('POST /add_image')
def add_image(con, request):
    if request.data['file'].filename: 
        DB[request.data['file'].filename] = request.data['file'].file.read()
    index(con, request)

if __name__ == '__main__':
    app.run()








