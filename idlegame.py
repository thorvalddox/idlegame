from flask import Flask,session,request,jsonify,render_template,make_response

import re
import json
import os
from itertools import chain
from collections import OrderedDict,Counter,namedtuple
from threading import Thread
from time import sleep
from random import randrange

app = Flask(__name__)

app.debug = True


class Resource:
    all_ = OrderedDict()

    def __init__(self, name, parent=None):
        self.parent = parent
        self.rawname = name
        if "*" in name:
            showname,subname = name.split("*")
        elif "@" in name:
            showname = name
            subname = name.replace("@","").strip()
        else:
            showname = "@"
            subname = name

        self.childfill = showname.replace("@","{}")
        if self.parent is None:
            self.displayname = subname
            self.pathname = subname
        else:
            self.displayname = self.parent.childfill.format(subname)
            self.pathname = self.parent.pathname + "/" + subname


        p = self
        self.level = -1
        while p is not None:
            p = p.parent
            self.level += 1

        Resource.all_[self.pathname] = self

    @property
    def get_children(self):
        for v in list(Resource.all_.values()): #list to prevent RuntimeError: dictionary changed size during iteration
            if v.parent == self:
                yield v

    def show(self,index=0):
        #yield ">" + "    "*index + self.pathname + "    ( " + self.displayname + " )"
        yield js_resourse(self)
        for r in self.get_children:
            for s in r.show(index + 1):
                yield s
    @staticmethod
    def show_all():
        for k,v in Resource.all_.items():
            if v.parent is None:
                for s in v.show():
                    yield s

    @staticmethod
    def get_by_path(path):
        return Resource.all_[path]

    @staticmethod
    def get_by_id(id_):
        for s in Resource.all_.values():
            if s.js_id == id_:
                return s
        assert True,"Invalid Id"  #Should not get here

    @staticmethod
    def load():
        print(os.getcwd())
        with open("resources.json") as file:
            data = json.load(file,object_pairs_hook=OrderedDict) #Ordered dict to force load order
            for k,v in data.items():
                Resource(k).unpack(v)


    def unpack(self,data):
        for k,v in data.items():
            if k.startswith("+"):
                for i in Resource.get_by_path(k[1:]).get_children:
                    Resource(i.rawname,self)
            else:
                Resource(k,self).unpack(v)

    @property
    def js_id(self):
        return self.pathname.replace("/","_").replace(" ","_")

    @property
    def pure(self):
        return any(True for _ in self.get_children)



def js_resourse(resource):
    if resource.pure:
        name =  ">" * resource.level + \
                "<a href=\"javascript:hide_{js_id}()\" id=\"button_{js_id}\">{name}</a>"\
                .format(name=resource.displayname,js_id=resource.js_id)
        show_funcs = "\n".join(
            """
            document.getElementById("row_{}").style.display = "";

            """.format(r.js_id) for r in resource.get_children)

        hide_funcs = "\n".join(
            """
            document.getElementById("row_{}").style.display = "none";

            """.format(r.js_id) for r in resource.get_children)
        autohide = "hide_{}();".format(resource.js_id)
    else:
        name = ">" * resource.level + resource.displayname
        show_funcs = ""
        hide_funcs = ""
        autohide = ""
    return """

    <tr id="row_{js_id}"">
        <td>
            {name}
        </td>
        <td>
            <div id="res_{js_id}">Invalid</div>
        <td>

    <script>
        {updater}
        function show_{js_id}()
        {{
            {show}
            document.getElementById("button_{js_id}").setAttribute("href","javascript:hide_{js_id}()")

        }}
        function hide_{js_id}()
        {{
            {hide}
            document.getElementById("button_{js_id}").setAttribute("href","javascript:show_{js_id}()")

        }}

        function load_{js_id}(){{
        {autohide}
        }}
        $(document).ready(load_{js_id});
    </script>
    </tr>


    """.format(name=name,js_id=resource.js_id,show=show_funcs,hide=hide_funcs,autohide=autohide,
               updater=autoupdater("/get_resourse/{}/".format(resource.js_id),"res_"+resource.js_id))

def autoupdater(path,html,unique=None):
    if unique is None:
        unique = html

    return """
        var xmlhttp_{id};
        if (window.XMLHttpRequest)
          {{// code for IE7+, Firefox, Chrome, Opera, Safari
          xmlhttp_{id}=new XMLHttpRequest();
          }}
        else
          {{// code for IE6, IE5
          xmlhttp_{id}=new ActiveXObject("Microsoft.XMLHTTP");
          }}
        xmlhttp_{id}.onreadystatechange=function()
          {{
          if (xmlhttp_{id}.readyState==4 && xmlhttp_{id}.status==200)
            {{
            document.getElementById("{html}").innerHTML=xmlhttp_{id}.responseText;
            }}
          }}

        function loadXMLDoc_{id}()
        {{
        xmlhttp_{id}.open("GET","{path}",true);
        xmlhttp_{id}.send();
        }}
        function load_{id}(){{
        var t=setInterval(loadXMLDoc_{id},5000);
        loadXMLDoc_{id}();
        }}
        $(document).ready(load_{id});
        """.format(id=unique,path=path,html=html)


class Player:
    all_ = {}
    def __init__(self,id_):
        self.id_ = id_
        self.resources = Counter((r,0) for r in Resource.all_.keys())
        self.plots = []
        Backclock(self).start()
        Player.all_[self.id_] = self


    @classmethod
    def get(cls):
        id_ = request.cookies.get("player_id",hex(randrange(16**16)))
        if id_ in cls.all_:
            return cls.all_[id_]
        else:
            return cls(id_)

    def get_resource(self,resource):
        return self.resources[resource.pathname] + sum(self.get_resource(r) for r in resource.get_children)

    def pay(self,mats):

        if all(self.resources[mat.path] >= mat.amount for mat in mats):
            self.resources -= {mat.path:mat.amount for mat in mats}
            return True
        return False
    def gain(self,mats):
        self.resources += {mat.path:mat.amount for mat in mats}


    def step(self):
        if self.resources["food"] >= 1000*len(self.plots):
            left = 1000*len(self.plots)
            for i in Resource.all_:
                if i.startswith("food") and self.resources[i]:
                    am = min(left,self.resources[i])
                    self.resources[i] -= am
                    left -= am
            Plot(self)
        for i in self.plots:
            i.step(self)
class Backclock(Thread):
    def __init__(self,player):
        Thread.__init__(self)
        self.player = player
    def run(self):
        while 1:
            sleep(2)
            self.player.step()
            print("updated" + self.player.id_)


Material = namedtuple("Material","path,amount")

def unittimes(unit):
    a,b = unit.split(":")
    return Material(a,int(b))

def display(mat):
    return "{} x{}".format(*mat)



class Reaction:
    def __init__(self,start,*ends):
        self.start = unittimes(start)
        self.ends = map(unittimes,ends)
    def get_creation(self,ingr):
        assert ingr.startswith(self.start.path)
        for e in self.ends:
            path,amount = e
            #example: start=metal/ore, end=metal/bar ingr=metal/ore/copper -> product=metal/bar + /copper
            product = path + ingr[len(self.start.path):]
            while product not in Resource.all_:
                product = "/".join(product.split("/")[:-1])
            yield Material(product,amount)

    def get_raws(self):
        for i in Resource.all_.values():
            if i.pathname.startswith(self.start.path):
                yield Reaction_Raw(Material(i.pathname,self.start.amount),list(self.get_creation(i.pathname)))



Reaction_Raw = namedtuple("RawReaction","start,endlist")

class Workshop():
    all_ = []
    def __init__(self,jsondict):
        self.reactions = []
        for i in jsondict["reactions"]:
            start = i.split("->")[0].strip()
            ends = [x.strip() for x in i.split("->")[1].split("+")]
            self.reactions.extend(Reaction(start,*ends).get_raws())
        self.cost = map(unittimes,jsondict["cost"])
        self.name = jsondict["name"]
        self.parentname = jsondict.get("parent",None)
        Workshop.all_.append(self)

    def step(self,active,player):
        if self.reactions:
            print(self.reactions)
            r = self.reactions[active % len(self.reactions)]
            if player.pay([r.start]):
                player.gain(r.endlist)
    def get_string_active(self,index):
        r = self.reactions[index % len(self.reactions)]
        return display(r.start) + " -> " + " + ".join(map(display,r.endlist))

    def get_children(self):
        for i in Workshop.all_:
            if i.parentname == self.name:
                yield i

    @staticmethod
    def load():
        with open("workshops.json") as file:
            data = json.load(file,object_pairs_hook=OrderedDict) #Ordered dict to force load order
            for d in data:
                Workshop(d)




class Plot:
    all_ = {}
    def __init__(self,player):
        self.id_ = hex(randrange(16**16))
        self.player = player
        player.plots.append(self)
        self.workshop = forest
        self.build = 0
        self.active = 0
        Plot.all_[self.id_] = self
    def step(self,player):
        if self.build > 0:
            if player.pay(self.workshop.cost):
                self.build -= 1
        else:
            self.workshop.step(self.active,player)
    def get_active(self):
        if self.build > 0:
            return "under construction"
        else:
            return self.workshop.get_string_active(self.active)
    def change_workshop(self,new):
        self.workshop = new
        self.build = 100
    @staticmethod  # static because None must be an option if it doesn't exist
    def show_plot(index):
        return \
        """
        <div>
            <td>
                <table id="plot_table_{index}" style="display: none;" style="border: double;">
                    <tr>
                        <td>
                            <div id="plot_name_{index}">plot name</div>
                        </td>
                        <td>
                            <a href="/workshop/upgrade/0/{index}" id="upgrade_0_{index}">upgrade 0<div></a>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <a href="/workshop/shift/left/{index}">&lt;-</a> <a href="/workshop/shift/right/{index}">-&gt;</a>
                        </td>
                        <td>
                            <a href="/workshop/upgrade/1/{index}" id="upgrade_1_{index}">upgrade 1<div></a>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <div id="plot_reaction_{index}">plot reaction</div>
                        </td>
                        <td>
                            <a href="/workshop/upgrade/2/{index}" id="upgrade_2_{index}">upgrade 2<div></a>
                        </td>
                    </tr>
                </table>
            </td>
        </div>
        <script>
            function load_plot_{index}(){{
            var t=setInterval(plot_update_{index},5000);
            plot_update_{index}();
            }}
            $(document).ready(load_plot_{index});
            function plot_update_{index}()
            {{
            if (document.getElementById("plot_name_{index}").innerHTML != "")
            {{
                document.getElementById("plot_table_{index}").style.display = "";
            }}
            else
            {{
                document.getElementById("plot_table_{index}").style.display = "none";
            }}
            }}
        </script>
        """.format(index=index) + "<script>\n" + \
        autoupdater("/workshop/get/name/{}/".format(index),"plot_name_{}".format(index)) + \
        autoupdater("/workshop/get/reaction/{}/".format(index),"plot_reaction_{}".format(index)) + \
        autoupdater("/workshop/get/0/{}/".format(index),"upgrade_0_{}".format(index)) + \
        autoupdater("/workshop/get/1/{}/".format(index),"upgrade_1_{}".format(index)) + \
        autoupdater("/workshop/get/2/{}/".format(index),"upgrade_2_{}".format(index)) + "</script>\n"


def pack_plots():
    yield "<table>"
    for i in range(20):
        yield "<tr>"
        for j in range(1):
            yield "<td>"
            yield Plot.show_plot(i+j)
            yield "</td>"
        yield "</tr>"
    yield "</table>"

@app.route('/')
def home():

    player = Player.get()
    response = make_response(render_template("game.html",resource_tree="\n".join(Resource.show_all()),
                                             plots = "\n".join(pack_plots())))
    response.set_cookie('player_id',value=Player.get().id_)
    return response


@app.route("/get_resourse/<js_id>/")
def get_resources(js_id):
    player = Player.get()
    return str(player.get_resource(Resource.get_by_id(js_id)))

@app.route("/workshop/shift/<dir>/<index>/")
def change_plot(dir,index):
    p = Player.get().plots[int(index)]
    p.active += {"left":-1,"right":1}[dir]
    return '', 204

@app.route("/workshop/upgrade/<upgrade>/<index>/")
def upgrade_plot(upgrade,index):
    if int(index) >= len(Player.get().plots):
        return ""
    p = Player.get().plots[int(index)]
    upgrade = ([c for c in p.workshop.get_children()]+[None]*3)[int(upgrade)]
    if upgrade is not None:
        p.change_workshop(upgrade)
    return '',204

@app.route("/workshop/get/name/<index>/")
def get_w_name(index):
    if int(index) >= len(Player.get().plots):
        return ""
    p = Player.get().plots[int(index)]
    return p.workshop.name

@app.route("/workshop/get/reaction/<index>/")
def get_w_reac(index):
    if int(index) >= len(Player.get().plots):
        return ""
    p = Player.get().plots[int(index)]
    return p.get_active()

@app.route("/workshop/get/<upgrade>/<index>/")
def get_w_route(upgrade,index):
    if int(index) >= len(Player.get().plots):
        return ""
    p = Player.get().plots[int(index)]
    return ([c.name for c in p.workshop.get_children()]+[""]*3)[int(upgrade)]

if __name__ == '__main__':
    Resource.load()
    Workshop.load()
    forest = Workshop.all_[0]
    app.run()
