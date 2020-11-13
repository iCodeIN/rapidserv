"""
"""

from rapidserv import RapidServ, core

app = RapidServ(__file__)

@app.accept
class Simple(object):
    def __init__(self, con):
        con.add_map('GET /', self.send_base)

    def send_base(self, con, request):
        HTML = """ <html> 
                   <body>
                   <p> It is simple :P </p>
                   </body> </html>
               """

        con.add_data(HTML)
        con.done()

if __name__ == '__main__':
    app.bind('0.0.0.0', 8000, 60)
    core.gear.mainloop()