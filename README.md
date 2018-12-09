# Rapidserv

A non-blocking Flask-like Web Framework in python.

Rapidserv is a micro web framework that shares with flask some similarities
Rapidserv is non blocking network I/O consequently it can scale a lot of connections and it is ideal for some applications. 
Rapidserv uses jinja2 although it doesn't enforce the usage.

~~~python
from rapidserv import RapidServ, core

app = RapidServ(__file__)

@app.request('GET /')
def send_base(con, request):
    con.add_data('<html> <body> <p> Rapidserv </p> </body> </html>')
    con.done()

if __name__ == '__main__':
    app.bind('0.0.0.0', 8000, 50)
    core.gear.mainloop()
~~~

# Install

Rapidserv would run python3+ only.

~~~
pip install -r requirements.txt
pip install rapidserv
~~~

# Documentation

[Wiki](https://github.com/iogf/rapidserv/wiki)


